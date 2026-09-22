# frozen_string_literal: true

require "securerandom"

module Simulate
  # Script-only Unipile extras (list accounts + poll). Product EmailClient stays unchanged.
  class Unipile < Email::EmailClient
    def accounts
      items = []
      cursor = nil
      loop do
        params = { limit: 100 }
        params[:cursor] = cursor if cursor.present?
        body = get("/api/v1/accounts", params)
        page = Array(body.is_a?(Hash) ? (body["items"] || body["data"]) : nil)
        items.concat(page)
        cursor = body.is_a?(Hash) ? (body["cursor"] || body["next_cursor"]) : nil
        break if page.empty? || cursor.blank?
      end
      items
    end

    def account_id_for!(email, prefer: nil)
      wanted = email.to_s.strip.downcase
      matches = accounts.select { |row| account_email(row) == wanted }
      raise "No Unipile account connected for #{wanted}. Connect it in Unipile first." if matches.blank?

      ranked = matches.sort_by do |row|
        hash = stringify(row)
        id = (hash["id"] || hash[:id]).to_s
        mail_rank = mail_source_ok?(hash) ? 0 : 1
        prefer_rank = prefer.present? && id == prefer.to_s ? 0 : 1
        google_rank = hash["type"].to_s.upcase.include?("GOOGLE") ? 0 : 1
        [ mail_rank, prefer_rank, google_rank ]
      end
      hit = stringify(ranked.first)
      id = (hit["id"] || hit[:id]).to_s
      unless mail_source_ok?(hit)
        raise "Unipile Gmail for #{wanted} is disconnected (MAILS=#{mail_source_status(hit)}). Reconnect #{wanted} in Unipile."
      end

      id
    end

    def send_message(account_id:, to:, subject:, body:, reply_to: nil, attachments: [])
      if Array(attachments).compact.empty?
        result = send_email(
          account_id: account_id,
          to: to,
          subject: subject,
          body: body,
          reply_to: reply_to
        )
        return stringify(result)
      end

      stringify(post_multipart_email(
        account_id: account_id,
        to: to,
        subject: subject,
        body: body,
        reply_to: reply_to,
        attachments: attachments
      ))
    end

    # Unipile 422 invalid_reply_subject unless this matches the parent (or Re: + parent).
    # Prefer the captured thread subject so we never GET a Gmail provider uid without account_id.
    def reply_subject(parent_id, fallback = nil, account_id: nil)
      original = fallback.to_s.strip
      if original.blank? && parent_id.present?
        parent = load_email(parent_id, account_id: account_id) || {}
        original = parent["subject"].to_s.strip
      end
      return "" if original.blank?
      return original if original.match?(/\A(Re|RE|re)\s*:/)

      "Re: #{original}"
    end

    def poll_email(account_id:, from:, search:, after:, timeout:, exclude_ids: [])
      deadline = Time.current + timeout
      fallback = nil
      loop do
        body = list_emails(
          account_id: account_id,
          from: from,
          search: search,
          after: after.utc.iso8601(3),
          limit: 20
        )
        items = Array(body.is_a?(Hash) ? (body["items"] || body["data"]) : nil)
        candidates = items.filter_map do |row|
          hash = stringify(row)
          id = email_id(hash)
          next if id.blank? || exclude_ids.include?(id)
          next unless matches_search?(hash, search)

          hash
        end
        full, stubs = candidates.partition { |row| row["kind"].to_s != "0_ref" }
        newest = ->(rows) { rows.sort_by { |row| row["date"].to_s }.reverse }
        (newest.call(full) + newest.call(stubs)).each do |row|
          loaded = load_email(email_id(row), account_id: account_id)
          return loaded if loaded.present?

          fallback ||= row
        end
        break if Time.current >= deadline

        sleep 2
      end
      fallback
    end

    # List can return kind=0_ref stubs / Gmail provider uids that GET 422 without account_id.
    def load_email(id, account_id: nil)
      return nil if id.blank?

      attempts = 0
      begin
        attempts += 1
        params = {}
        params[:account_id] = account_id if account_id.present?
        stringify(get("/api/v1/emails/#{id}", params))
      rescue Faraday::Error => e
        detail = e.message.to_s
        return nil if detail.match?(/404|not found|422|provider uid|Account id is required/i)

        raise if attempts >= 3

        sleep attempts
        retry
      end
    end

    def email_id(row)
      hash = stringify(row)
      candidates = [ hash["id"], hash["email_id"], hash["provider_id"] ].map(&:presence).compact
      candidates.find { |id| unipile_style_id?(id) } || candidates.first
    end

    def thread_id(row)
      hash = stringify(row)
      hash["thread_id"].presence || hash["id"].presence
    end

    private

    def account_email(row)
      hash = stringify(row)
      (
        hash["name"].presence ||
        hash.dig("connection_params", "mail") ||
        hash.dig("object", "name")
      ).to_s.strip.downcase
    end

    def mail_source(row)
      Array(stringify(row)["sources"]).find do |source|
        sid = source.is_a?(Hash) ? source["id"].to_s : source.to_s
        sid.include?("MAIL")
      end
    end

    def mail_source_status(row)
      source = mail_source(row)
      return stringify(row)["status"].to_s if source.blank?

      source.is_a?(Hash) ? source["status"].to_s : source.to_s
    end

    def mail_source_ok?(row)
      mail_source_status(row).casecmp("OK").zero?
    end

    def matches_search?(row, search)
      needle = search.to_s.downcase
      return true if needle.blank?

      haystack = "#{row['subject']} #{row['body']} #{row['body_plain']} #{row['snippet']}".downcase
      return true if haystack.blank?

      haystack.include?(needle)
    end

    def unipile_style_id?(value)
      token = value.to_s
      return false if token.blank?
      return false if token.match?(/\A[0-9a-f]{10,}\z/i)

      true
    end

    def stringify(value)
      return {} if value.blank?
      return value.stringify_keys if value.respond_to?(:stringify_keys)

      value
    end

    # v1 send-with-files is multipart. Product JSON send stays text-only.
    def post_multipart_email(account_id:, to:, subject:, body:, reply_to:, attachments:)
      boundary = "----Scotive#{SecureRandom.hex(8)}"
      chunks = []
      append_form_field(chunks, boundary, "account_id", account_id)
      append_form_field(chunks, boundary, "subject", subject.to_s)
      append_form_field(chunks, boundary, "body", body.to_s)
      append_form_field(chunks, boundary, "to", [ { identifier: to } ].to_json)
      append_form_field(chunks, boundary, "reply_to", reply_to) if reply_to.present?
      Array(attachments).each do |file|
        filename = file[:filename].presence || "invoice.pdf"
        content_type = file[:content_type].presence || "application/pdf"
        bytes = file[:content]
        next if bytes.nil? || bytes.bytesize.zero?

        chunks << "--#{boundary}\r\n"
        chunks << "Content-Disposition: form-data; name=\"attachments\"; filename=\"#{filename}\"\r\n"
        chunks << "Content-Type: #{content_type}\r\n\r\n"
        chunks << bytes
        chunks << "\r\n"
      end
      chunks << "--#{boundary}--\r\n"

      response = multipart_connection.post("/api/v1/emails") do |req|
        req.headers["Accept"] = "application/json"
        req.headers["Content-Type"] = "multipart/form-data; boundary=#{boundary}"
        req.body = chunks.map { |part| part.to_s.b }.join
      end
      unwrap!(response, "Unipile POST /api/v1/emails")
    end

    def append_form_field(chunks, boundary, name, value)
      chunks << "--#{boundary}\r\n"
      chunks << "Content-Disposition: form-data; name=\"#{name}\"\r\n\r\n"
      chunks << value.to_s
      chunks << "\r\n"
    end

    def multipart_connection
      @multipart_connection ||= Faraday.new(url: dsn) do |f|
        f.response :json, content_type: /\bjson$/
        f.headers["X-API-KEY"] = api_key
        f.options.timeout = 30
        f.adapter Faraday.default_adapter
      end
    end
  end
end
