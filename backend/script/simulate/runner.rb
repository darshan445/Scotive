# frozen_string_literal: true

require "base64"
require "json"
require "openssl"
require "yaml"

require_relative "qbo_writer"
require_relative "qbo_invoice_mail"
require_relative "unipile"

module Simulate
  # Seeds QBO + Unipile conversations, then calls the same interactors the UI uses.
  class Runner
  MODES = %w[onboarding sync webhook all].freeze

  def self.from_argv(argv)
    options = {
      "mode" => env_or("SIMULATE_MODE", "all"),
      "file" => env_or("SIMULATE_FILE", Rails.root.join("script/simulate/scenario.yml").to_s),
      "user" => env_or("SIMULATE_USER", nil),
      "wait" => env_or("SIMULATE_WAIT", nil)
    }
    argv.each do |arg|
      next unless arg.start_with?("--")
      next if arg == "--"

      key, value = arg.delete_prefix("--").split("=", 2)
      options[key] = value.nil? ? true : value
    end
    new(options)
  end

  def self.env_or(name, fallback)
    ENV[name].presence || fallback
  end

  def initialize(options)
    @options = options.stringify_keys
    @scenario = load_scenario
    @qbo = Simulate::QboWriter.new
    @mail = Simulate::Unipile.new
    @created = []
  end

  def run!
    Rails.application.reloader.wrap do
      with_inline_jobs do
        log "mode=#{mode} user=#{user.email} org=#{organization.id}"
        assert_connections!
        if resume?
          load_existing_seeds!
        else
          seed_invoices!
          play_conversations!(ingest_webhooks: %w[webhook all].include?(mode))
        end
        refresh_records!
        run_onboarding! if %w[onboarding all].include?(mode)
        refresh_records!
        run_sync! if %w[sync all].include?(mode)
        print_snapshot
        assert_expectations!
      end
    end
  end

  private

  attr_reader :options, :scenario, :qbo, :mail, :created

  def mode
    value = options["mode"].to_s
    raise "Unknown mode #{value.inspect}. Use #{MODES.join(', ')}" unless MODES.include?(value)

    value
  end

  def user
    @user ||= begin
      email = (options["user"].presence || scenario["user_email"]).to_s.strip.downcase
      raise "Set user_email in the scenario or pass --user=" if email.blank?

      record = User.find_by(email: email)
      raise "No user #{email}. Sign up / log in first." if record.blank?

      record
    end
  end

  def organization
    @organization ||= user.organization
  end

  def accounting
    @accounting ||= organization.integrations.accounting.connected.find_by(provider: "qbo")
  end

  def mailbox
    @mailbox ||= organization.integrations.mailbox.connected.first
  end

  def user_mailbox_email
    (options["user_mailbox"].presence || scenario["user_mailbox"] || mailbox&.account_name).to_s.strip.downcase
  end

  def client_email
    (options["client_email"].presence || scenario["client_email"]).to_s.strip.downcase
  end

  def wait_seconds
    (options["wait"].presence || scenario["wait_seconds"] || 8).to_i
  end

  def send_from_qbo?
    flag = options["send-from-qbo"]
    return truthy?(flag) unless flag.nil?
    return truthy?(scenario["send_from_qbo"]) if scenario.key?("send_from_qbo")

    true
  end

  def skip_emails?
    truthy?(options["skip-emails"])
  end

  def resume?
    truthy?(options["resume"])
  end

  def refresh_records!
    return if @user.blank?

    @user = User.find(@user.id)
    @organization = @user.organization
    @accounting = nil
    @mailbox = nil
  end

  def load_existing_seeds!
    invoices_config.each do |row|
      number = row["number"].to_s
      local = organization.invoices.find_by(invoice_number: number)
      raise "Resume: local invoice #{number} is missing. Run without --resume first." if local.blank?

      created << {
        config: row,
        remote: { "Id" => local.external_id, "DocNumber" => number },
        invoice_number: number,
        amount: local.total_amount,
        due_date: local.due_date,
        pay_link: nil,
        messages: [],
        threads: {},
        last_thread_for: { "user" => "invoice", "client" => "invoice" }
      }
      log "resume #{number} local=#{local.id} bucket=#{local.list_bucket} threads=#{local.invoice_conversations.size}"
    end
  end

  def user_unipile_id
    @user_unipile_id ||= mail.account_id_for!(user_mailbox_email, prefer: mailbox&.external_account_id)
  end

  def client_unipile_id
    @client_unipile_id ||= mail.account_id_for!(client_email)
  end

  def assert_connections!
    raise "QuickBooks is not connected for #{user.email}" if accounting.blank?
    raise "Gmail/Outlook is not connected for #{user.email}" if mailbox.blank?
    raise "Set client_email in the scenario" if client_email.blank?
    raise "Mailbox account_name #{mailbox.account_name} does not match #{user_mailbox_email}" if mailbox.account_name.to_s.downcase != user_mailbox_email

    remount_mailbox_if_stale!
    log "QBO realm=#{accounting.external_account_id} mailbox=#{mailbox.account_name} (#{mailbox.external_account_id})"
    log "Unipile user=#{user_mailbox_email} (#{user_unipile_id}) client=#{client_email} (#{client_unipile_id})"
  end

  # Gmail can be reconnected in Unipile while Scotive still stores the old account id
  # (MAILS=CREDENTIALS). Matching, sync, and webhooks use integrations.external_account_id.
  def remount_mailbox_if_stale!
    live_id = user_unipile_id.to_s
    stored_id = mailbox.external_account_id.to_s
    return if stored_id == live_id

    log "Mailbox Unipile id #{stored_id} is stale; pointing at live #{live_id} for #{user_mailbox_email}"
    mailbox.update!(external_account_id: live_id)
  end

  def seed_invoices!
    token = qbo.access_token_for(accounting)
    realm = accounting.external_account_id
    customer = qbo.find_or_create_customer(
      realm_id: realm,
      access_token: token,
      email: client_email,
      display_name: scenario["client_name"].presence || "AR Sim #{client_email}"
    )
    log "QBO customer #{customer['DisplayName']} id=#{customer['Id']}"

    invoices_config.each do |row|
      due = due_date_for(row)
      issue = issue_date_for(row, due)
      amount = BigDecimal(row["amount"].to_s)
      remote = qbo.create_invoice(
        realm_id: realm,
        access_token: token,
        customer_id: customer["Id"],
        amount: amount,
        due_date: due,
        issue_date: issue,
        email: client_email,
        description: row["description"],
        doc_number: row["number"]
      )
      seed = {
        config: row,
        remote: remote,
        invoice_number: remote["DocNumber"].presence || row["number"].to_s,
        amount: amount,
        due_date: due,
        pay_link: remote["InvoiceLink"].presence,
        messages: [],
        threads: {},
        last_thread_for: { "user" => "invoice", "client" => "invoice" }
      }
      created << seed
      log "QBO invoice #{seed[:invoice_number]} id=#{remote['Id']} $#{amount} due=#{due}"
      email_invoice!(seed, token, realm) if email_invoice?(seed)
      ingest_qbo_webhook!(remote) if %w[webhook all].include?(mode)
    end
  end

  def send_cfg(seed)
    (seed[:config]["send"] || {}).stringify_keys
  end

  def email_invoice?(seed)
    return false unless send_from_qbo?

    cfg = send_cfg(seed)
    return false if cfg.key?("enabled") && falsey?(cfg["enabled"])

    via = cfg["via"].to_s.strip.downcase
    return false if %w[none skip off false].include?(via)

    true
  end

  def send_via(seed)
    cfg = send_cfg(seed)
    raw = cfg["via"].to_s.strip.downcase
    return "mailbox" if %w[mailbox mail gmail personal].include?(raw)
    return "plain" if %w[plain token].include?(raw) || truthy?(cfg["plain"])

    "qbo"
  end

  def send_from_email(seed)
    raw = send_cfg(seed)["from"].to_s.strip.downcase
    return user_mailbox_email if raw.blank? || %w[default user me].include?(raw)

    raw
  end

  def email_invoice!(seed, token, realm)
    cfg = send_cfg(seed)
    message = interpolate(cfg["message"].presence || cfg["body"].to_s, seed)
    register_thread!(seed, "invoice", subject: invoice_send_subject(seed))
    apply_customer_memo_if_present!(seed, token, realm, message)
    via = send_via(seed)
    if via == "plain"
      send_invoice_plain!(seed, token, realm)
    elsif via == "qbo" && cfg["subject"].blank? && !unique_invoice_subjects?
      send_invoice_via_qbo!(seed, token, realm)
    else
      if via == "qbo"
        log "QBO /send cannot set a unique subject; mailbox-sending #{seed[:invoice_number]} so Gmail does not group threads"
      end
      send_invoice_via_mailbox!(seed, token, realm)
    end
  end

  def unique_invoice_subjects?
    flag = options.key?("unique-subjects") ? options["unique-subjects"] : scenario.fetch("unique_subjects", true)
    !falsey?(flag)
  end

  def invoice_company_name
    scenario["company_name"].presence || "Craig's Design and Landscaping Services"
  end

  def invoice_send_subject(seed, company_name = invoice_company_name)
    raw = send_cfg(seed)["subject"].presence || "Invoice {{invoice_number}} from #{company_name}"
    interpolate(raw, seed)
  end

  def falsey?(value)
    %w[0 false no off].include?(value.to_s.strip.downcase)
  end

  def apply_customer_memo_if_present!(seed, token, realm, message)
    return if message.blank?

    seed[:remote] = qbo.apply_customer_memo!(
      realm_id: realm,
      access_token: token,
      invoice: seed[:remote],
      memo: message
    )
    log "QBO invoice message (CustomerMemo) set"
  rescue Faraday::ConnectionFailed, Faraday::TimeoutError, SocketError => e
    log "skip CustomerMemo (#{e.message})"
  end

  def send_invoice_via_qbo!(seed, token, realm)
    qbo.send_invoice(
      realm_id: realm,
      access_token: token,
      invoice_id: seed[:remote]["Id"],
      email: client_email
    )
    log "QBO sent invoice #{seed[:invoice_number]} to #{client_email} (From is QBO company default)"
    sent_at = Time.current
    sleep wait_seconds
    captured = capture_mailbox!(
      seed,
      "invoice",
      role: "client",
      search: seed[:invoice_number],
      from: nil,
      after: sent_at - 30.seconds
    )
    if captured.blank?
      raise "QBO invoice email never appeared in #{client_email} for #{seed[:invoice_number]}"
    end
    log "invoice thread subject=#{seed.dig(:threads, 'invoice', :subject).inspect} client=#{seed.dig(:threads, 'invoice', :ids, 'client')}"
  rescue Faraday::Error, SocketError => e
    log "QBO send failed: #{e.message}"
    raise
  end

  def send_invoice_via_mailbox!(seed, token, realm)
    from_email = send_from_email(seed)
    remote = qbo.invoice_for_email(realm_id: realm, access_token: token, invoice_id: seed[:remote]["Id"])
    seed[:remote] = remote
    seed[:pay_link] = remote["InvoiceLink"].presence || seed[:pay_link]
    pdf = qbo.invoice_pdf(realm_id: realm, access_token: token, invoice_id: remote["Id"])
    company = qbo.company_name(realm_id: realm, access_token: token)
    subject = invoice_send_subject(seed, company)
    mailer = Simulate::QboInvoiceMail.build(invoice: remote, company_name: company, subject: subject)
    prefer = from_email == user_mailbox_email ? mailbox.external_account_id : nil
    account_id = mail.account_id_for!(from_email, prefer: prefer)
    log "mailbox invoice #{seed[:invoice_number]} from #{from_email} subject=#{mailer[:subject].inspect}"
    sent_at = Time.current
    sent = mail.send_message(
      account_id: account_id,
      to: client_email,
      subject: mailer[:subject],
      body: mailer[:html],
      reply_to: nil,
      attachments: [
        { filename: mailer[:filename], content: pdf, content_type: "application/pdf" }
      ]
    )
    begin
      seed[:remote] = qbo.mark_email_sent!(realm_id: realm, access_token: token, invoice: remote)
    rescue Faraday::Error => e
      log "skip QBO EmailStatus (#{e.message})"
    end
    observe_delivery!(seed, "invoice", "user", sent, sent_at, mailer[:subject], false)
  end

  # Owner send with a custom body and no QBO PDF — used for token-only HOME.
  def send_invoice_plain!(seed, token, realm)
    from_email = send_from_email(seed)
    remote = qbo.invoice_for_email(realm_id: realm, access_token: token, invoice_id: seed[:remote]["Id"])
    seed[:remote] = remote
    seed[:pay_link] = remote["InvoiceLink"].presence || seed[:pay_link]
    subject = invoice_send_subject(seed)
    body = interpolate(send_cfg(seed)["message"].presence || "Pay here: {{pay_link}}", seed)
    prefer = from_email == user_mailbox_email ? mailbox.external_account_id : nil
    account_id = mail.account_id_for!(from_email, prefer: prefer)
    log "plain invoice #{seed[:invoice_number]} from #{from_email} subject=#{subject.inspect}"
    sent_at = Time.current
    sent = mail.send_message(
      account_id: account_id,
      to: client_email,
      subject: subject,
      body: body,
      reply_to: nil
    )
    begin
      seed[:remote] = qbo.mark_email_sent!(realm_id: realm, access_token: token, invoice: remote)
    rescue Faraday::Error => e
      log "skip QBO EmailStatus (#{e.message})"
    end
    observe_delivery!(seed, "invoice", "user", sent, sent_at, subject, false)
  end

  def play_conversations!(ingest_webhooks:)
    return log("skip emails") if skip_emails?

    created.each do |seed|
      conversation_turns(seed[:config]).each_with_index do |turn, index|
        play_turn!(seed, turn, index: index, ingest_webhooks: ingest_webhooks)
      end
    end
  end

  def play_turn!(seed, turn, index:, ingest_webhooks:)
    from_role = role_for(turn["from"])
    to_email = recipient_for(turn, from_role)
    thread_name, reply_to = resolve_thread!(seed, turn, from_role)
    subject = if reply_to.present?
      mail.reply_subject(
        reply_to,
        seed.dig(:threads, thread_name, :subject),
        account_id: from_role == "user" ? user_unipile_id : client_unipile_id
      )
    else
      interpolate(turn["subject"].presence || default_subject_for(seed, thread_name, false), seed)
    end
    body = interpolate(turn["body"].to_s, seed)
    raise "Conversation turn #{index} is missing body" if body.blank?
    raise "thread: new needs a subject (turn #{index})" if reply_to.blank? && turn["subject"].blank? && thread_mode(turn) == "new"

    account_id = from_role == "user" ? user_unipile_id : client_unipile_id
    sent_at = Time.current
    log "send #{from_role} → #{to_email} thread=#{thread_name} #{reply_to.present? ? 'reply' : 'new'} subject=#{subject.inspect}"
    sent = mail.send_message(
      account_id: account_id,
      to: to_email,
      subject: subject,
      body: body,
      reply_to: reply_to
    )
    observe_delivery!(seed, thread_name, from_role, sent, sent_at, subject, ingest_webhooks)
  end

  def thread_mode(turn)
    raw = turn["thread"].to_s.strip.downcase
    return "new" if truthy?(turn["new"]) || raw == "new"
    return "new" if turn.key?("reply") && !truthy?(turn["reply"])
    return "existing" if raw.blank? || %w[existing invoice qbo].include?(raw)

    raw
  end

  def resolve_thread!(seed, turn, from_role)
    mode = thread_mode(turn)
    if mode == "new"
      name = turn["as"].presence || "thread-#{seed[:threads].size + 1}"
      register_thread!(seed, name, subject: interpolate(turn["subject"].to_s, seed))
      [ name, nil ]
    else
      name = mode == "last" ? (seed[:last_thread_for][from_role] || "invoice") : (mode == "existing" ? "invoice" : mode)
      thread = seed[:threads][name]
      raise "Unknown thread #{name.inspect}. Use existing, new, last, or as: name from a prior new email." if thread.blank?

      reply_id = thread[:ids][from_role]
      log "thread #{name} has no #{from_role}-side message yet; sending without reply_to" if reply_id.blank?
      [ name, reply_id ]
    end
  end

  def register_thread!(seed, name, subject:)
    seed[:threads][name] ||= { subject: subject.presence, ids: { "user" => nil, "client" => nil }, seen_ids: [] }
    seed[:threads][name][:subject] = subject if subject.present? && seed[:threads][name][:subject].blank?
    seed[:threads][name]
  end

  def observe_delivery!(seed, thread_name, from_role, sent, sent_at, subject, ingest_webhooks)
    thread = register_thread!(seed, thread_name, subject: subject)
    sent_id = mail.email_id(sent)
    thread[:ids][from_role] = sent_id if sent_id.present?
    thread[:seen_ids] << sent_id if sent_id.present?
    seed[:last_thread_for][from_role] = thread_name
    seed[:messages] << { role: from_role, sent_id: sent_id, thread: thread_name }
    sleep wait_seconds

    recipient = from_role == "user" ? "client" : "user"
    received = capture_mailbox!(
      seed,
      thread_name,
      role: recipient,
      search: search_needle(seed, subject),
      from: from_role == "user" ? user_mailbox_email : client_email,
      after: sent_at - 30.seconds
    )
    seed[:last_thread_for][recipient] = thread_name
    if recipient == "user"
      raise "Mail from #{client_email} never appeared in #{user_mailbox_email} (#{subject})" if received.blank?

      ingest_mailbox_webhook!(received) if ingest_webhooks
    elsif received.blank?
      log "Mail from #{user_mailbox_email} not yet visible on #{client_email} for thread #{thread_name}"
    end
  end

  def capture_mailbox!(seed, thread_name, role:, search:, from:, after: 5.minutes.ago)
    thread = seed[:threads][thread_name]
    account_id = role == "user" ? user_unipile_id : client_unipile_id
    found = mail.poll_email(
      account_id: account_id,
      from: from,
      search: search,
      after: after,
      timeout: [ wait_seconds * 6, 45 ].max,
      exclude_ids: Array(thread&.dig(:seen_ids))
    )
    return if found.blank?

    id = mail.email_id(found)
    thread[:ids][role] = id
    thread[:seen_ids] << id
    thread[:subject] = found["subject"] if found["subject"].present?
    found
  end

  def search_needle(seed, subject)
    number = seed[:invoice_number].to_s
    return number if number.present? && subject.to_s.include?(number)

    subject.to_s.sub(/\ARe:\s*/i, "").truncate(80, omission: "")
  end

  def default_subject_for(seed, thread_name, is_reply)
    base = seed.dig(:threads, thread_name, :subject).presence || "Invoice #{seed[:invoice_number]}"
    base = base.sub(/\ARe:\s*/i, "")
    is_reply ? "Re: #{base}" : base
  end

  def run_onboarding!
    log "UI path: POST /api/v1/qbo/imports → Quickbooks::ImportOpenInvoices"
    data = must!(Quickbooks::ImportOpenInvoices.execute(organization: organization), "import")
    log "import #{data.inspect}"

    log "UI path: POST /api/v1/qbo/pipelines/match → Quickbooks::EnqueueConversationMatch"
    begin
      matched = must!(Quickbooks::EnqueueConversationMatch.execute(organization: Organization.find(organization.id), client: mail), "match")
      log "match #{matched.inspect}"
    rescue RuntimeError => e
      raise unless e.message.to_s.match?(/State reader/)

      log "match linked threads; AI state reader failed (#{e.message})"
      log "threads are saved. OpenAI failed while jobs ran inline — check OPENAI_API_KEY / quota / api.openai.com"
    end

    continue = Onboarding::Continue.execute(organization: organization)
    log continue.success? ? "onboarding continue → dashboard" : "onboarding continue skipped: #{Array(continue.errors).join(', ')}"
  end

  def run_sync!
    rewind_sync_cursors!
    Sync::State.clear_running!(organization.id)
    log "UI path: POST /api/v1/sync → Sync::Start → Sync::RunNow"
    started = must!(Sync::Start.execute(organization: organization), "sync")
    log "sync #{started.inspect}"
  end

  def rewind_sync_cursors!
    since = 3.hours.ago
    accounting.update!(last_synced_at: since) if accounting.last_synced_at.present? && accounting.last_synced_at > since
    mailbox.update!(last_synced_at: since) if mailbox.last_synced_at.present? && mailbox.last_synced_at > since
  end

  def ingest_qbo_webhook!(remote)
    token = ENV["QBO_WEBHOOK_VERIFIER_TOKEN"].to_s
    if token.blank?
      log "skip QBO webhook (QBO_WEBHOOK_VERIFIER_TOKEN blank)"
      return
    end

    payload = {
      "eventNotifications" => [
        {
          "realmId" => accounting.external_account_id,
          "dataChangeEvent" => {
            "entities" => [
              {
                "name" => "Invoice",
                "id" => remote["Id"].to_s,
                "operation" => "Create",
                "lastUpdated" => Time.current.utc.iso8601(3)
              }
            ]
          }
        }
      ]
    }
    raw = payload.to_json
    signature = Base64.strict_encode64(OpenSSL::HMAC.digest("SHA256", token, raw))
    log "UI path: POST /api/qbo/webhooks → Webhooks::Ingest(qbo)"
    must!(Webhooks::Ingest.execute(provider: "qbo", raw_body: raw, signature: signature), "qbo webhook")
  end

  def ingest_mailbox_webhook!(received)
    secret = ENV["UNIPILE_WEBHOOK_SECRET"].to_s
    if secret.blank?
      log "skip mailbox webhook (UNIPILE_WEBHOOK_SECRET blank)"
      return
    end

    payload = {
      "event" => "mail_received",
      "account_id" => mailbox.external_account_id,
      "email_id" => mail.email_id(received),
      "thread_id" => mail.thread_id(received),
      "is_complete" => false
    }
    raw = payload.to_json
    log "UI path: POST /api/v1/gmail/webhooks → Webhooks::Ingest(gmail) email_id=#{payload['email_id']}"
    must!(Webhooks::Ingest.execute(provider: "gmail", raw_body: raw, signature: secret), "mailbox webhook")
  end

  def print_snapshot
    numbers = created.map { |seed| seed[:invoice_number] }
    rows = organization.invoices.where(invoice_number: numbers).includes(:client, invoice_conversations: :conversation)
    log "--- snapshot ---"
    if rows.empty?
      log "no local invoices yet (webhook/sync/onboarding did not persist)"
      return
    end

    rows.each do |invoice|
      message_count = Message.joins(conversation: :invoice_conversations)
        .where(invoice_conversations: { invoice_id: invoice.id })
        .count
      log [
        invoice.invoice_number,
        "bucket=#{invoice.list_bucket}",
        "books=#{invoice.books_status}",
        "chase=#{invoice.chase_status}",
        "wait=#{invoice.expected_pay_date}",
        "balance=#{invoice.balance_remaining}",
        "threads=#{invoice.invoice_conversations.size}",
        "messages=#{message_count}",
        "inbound=#{invoice.last_human_inbound_at.present?}"
      ].join(" ")
      invoice.invoice_conversations.each do |link|
        conversation = link.conversation
        log "    #{link.is_primary? ? 'HOME' : 'split'} #{conversation.external_thread_id} #{conversation.subject.inspect}"
      end
    end
  end

  def assert_expectations!
    failures = []
    created.each do |seed|
      expected = (seed[:config]["expect"] || {}).stringify_keys
      next if expected.blank?

      invoice = organization.invoices.find_by(invoice_number: seed[:invoice_number])
      if invoice.blank?
        failures << "#{seed[:invoice_number]} missing locally"
        next
      end

      if expected.key?("bucket") && invoice.list_bucket != expected["bucket"].to_s
        failures << "#{invoice.invoice_number} bucket=#{invoice.list_bucket} want #{expected['bucket']}"
      end
      threads = invoice.invoice_conversations.size
      if expected.key?("min_threads") && threads < expected["min_threads"].to_i
        failures << "#{invoice.invoice_number} threads=#{threads} want >= #{expected['min_threads']}"
      end
      if expected.key?("max_threads") && threads > expected["max_threads"].to_i
        failures << "#{invoice.invoice_number} threads=#{threads} want <= #{expected['max_threads']}"
      end
      inbound = invoice.last_human_inbound_at.present?
      if expected.key?("inbound") && inbound != truthy?(expected["inbound"])
        failures << "#{invoice.invoice_number} inbound=#{inbound} want #{expected['inbound']}"
      end
    end

    if failures.empty?
      log "expectations ok"
      return
    end

    raise "Scenario expectations failed:\n  #{failures.join("\n  ")}"
  end

  def invoices_config
    rows = Array(scenario["invoices"])
    raise "scenario.invoices must be a non-empty array" if rows.empty?

    rows.map { |row| row.stringify_keys }
  end

  def conversation_turns(invoice_row)
    if invoice_row["conversations"].present?
      return Array(invoice_row["conversations"]).map { |row| row.stringify_keys }
    end

    from_turns = Array(invoice_row["from"]).map { |row| row.stringify_keys.merge("from" => "user") }
    to_turns = Array(invoice_row["to"]).map { |row| row.stringify_keys.merge("from" => "client") }
    turns = []
    [ from_turns.size, to_turns.size ].max.times do |index|
      turns << from_turns[index] if from_turns[index]
      turns << to_turns[index] if to_turns[index]
    end
    turns
  end

  def role_for(value)
    case value.to_s.strip.downcase
    when "", "user", "owner", user_mailbox_email then "user"
    when "client", "customer", client_email then "client"
    else
      raise "Unknown conversation from=#{value.inspect} (use user or client)"
    end
  end

  def recipient_for(turn, from_role)
    explicit = turn["to"].to_s.strip.downcase
    return explicit if explicit.present? && %w[user client owner].exclude?(explicit)

    from_role == "user" ? client_email : user_mailbox_email
  end

  def interpolate(text, seed)
    text.to_s
      .gsub("{{invoice_number}}", seed[:invoice_number].to_s)
      .gsub("{{amount}}", format("%.2f", seed[:amount]))
      .gsub("{{due_date}}", seed[:due_date].to_s)
      .gsub("{{pay_link}}", seed[:pay_link].to_s)
      .gsub("{{client_email}}", client_email)
      .gsub("{{user_email}}", user_mailbox_email)
  end

  def due_date_for(row)
    return Date.parse(row["due_date"].to_s) if row["due_date"].present?

    Date.current + row.fetch("due_in_days", 7).to_i
  end

  def issue_date_for(row, due)
    return Date.parse(row["issue_date"].to_s) if row["issue_date"].present?
    return due - 14 if due < Date.current

    Date.current
  end

  def load_scenario
    path = options["file"].to_s
    raise "Scenario file missing: #{path}" unless File.exist?(path)

    loaded = YAML.safe_load(File.read(path), permitted_classes: [ Date, Time ], aliases: true)
    (loaded || {}).stringify_keys
  end

  def must!(result, label)
    unless result.success?
      raise "#{label} failed: #{Array(result.errors).join(', ')}"
    end

    result.data
  end

  def with_inline_jobs
    previous = ActiveJob::Base.queue_adapter
    ActiveJob::Base.queue_adapter = :inline
    yield
  ensure
    ActiveJob::Base.queue_adapter = previous
  end

  def truthy?(value)
    %w[1 true yes on].include?(value.to_s.strip.downcase)
  end

  def log(message)
    puts("[simulate #{Time.current.strftime('%H:%M:%S')}] #{message}")
  end
end
end
