# frozen_string_literal: true

# Demo invoices for the chase workbench. Does not touch live QBO rows
# (external_id that is not demo-*). Re-run is idempotent.
#
#   docker compose exec api bin/rails runner script/seed_chase_demo.rb
#   docker compose exec api bin/rails runner script/seed_chase_demo.rb -- --email=testuser@gmail.com

email = "testuser@gmail.com"
ARGV.each { |arg| email = Regexp.last_match(1) if arg =~ /\A--email=(.+)\z/ }

user = User.find_by(email: email)
raise "No user #{email}" if user.blank?

org = user.organization
qbo = org.integrations.find_by(category: "accounting") || org.integrations.order(:created_at).first
mailbox = org.integrations.find_by(category: "mailbox") || qbo
raise "No integration on #{org.name}" if qbo.blank?

today = org.today
owner = mailbox.account_name.presence || user.email

demo_clients = org.clients.where("external_id LIKE ?", "demo-%")
org.invoices.where(client_id: demo_clients.select(:id)).find_each(&:destroy)
demo_clients.find_each(&:destroy)
org.conversations.where("external_thread_id LIKE ?", "demo-thread-%").find_each(&:destroy)

def upsert_client(org, qbo, key, name, email)
  org.clients.create!(
    integration: qbo,
    external_id: "demo-#{key}",
    name: name,
    primary_email: email,
    domain: email.split("@").last,
    associated_emails: [email]
  )
end

def create_invoice(org, qbo, client, number:, due:, amount:, chase:, books: "open", expected: nil, inbound_at: nil)
  org.invoices.create!(
    integration: qbo,
    client: client,
    external_id: "demo-#{number}",
    invoice_number: number,
    issue_date: due - 20,
    due_date: due,
    total_amount: amount,
    balance_remaining: books == "paid" || books == "voided" ? 0 : amount,
    books_status: books,
    chase_status: chase,
    expected_pay_date: expected,
    last_human_inbound_at: inbound_at
  )
end

def attach_thread(org, mailbox, invoice, owner:, client_email:, inbound: nil, outbound_body: nil)
  conversation = org.conversations.create!(
    integration: mailbox,
    external_thread_id: "demo-thread-#{invoice.invoice_number}",
    subject: "Invoice #{invoice.invoice_number}",
    status: "active"
  )
  InvoiceConversation.create!(invoice: invoice, conversation: conversation, is_primary: true, created_at: Time.current)
  sent = invoice.issue_date.to_time.change(hour: 10) + 2.hours
  outbound = conversation.messages.create!(
    external_message_id: "demo-out-#{invoice.invoice_number}",
    direction: "user_to_client",
    from_address: owner,
    to_addresses: [client_email],
    sent_at: sent,
    clean_body: outbound_body || "Hi — invoice #{invoice.invoice_number} for $#{invoice.total_amount.to_i} is attached. Pay when you can.",
    is_anchor: true,
    automatic: false,
    created_at: sent
  )
  return outbound unless inbound

  inbound_at = inbound[:at] || 10.hours.ago
  message = conversation.messages.create!(
    external_message_id: "demo-in-#{invoice.invoice_number}",
    direction: "client_to_user",
    from_address: client_email,
    to_addresses: [owner],
    sent_at: inbound_at,
    clean_body: inbound[:body],
    is_anchor: false,
    automatic: false,
    created_at: inbound_at
  )
  invoice.update!(last_human_inbound_at: inbound_at, last_human_inbound_message: message)
  invoice.invoice_chase_events.create!(
    event_type: "human_inbound",
    actor: "system",
    message: message,
    quote: inbound[:body].to_s.truncate(220),
    created_at: inbound_at
  )
  message
end

def queue_outbox(org, invoice, step:, status:, at: Time.current)
  invoice.outbox_messages.create!(
    organization: org,
    status: status,
    cadence_step: step,
    to_address: invoice.client.primary_email,
    subject: "Invoice #{invoice.invoice_number}",
    body: "Reminder for invoice #{invoice.invoice_number}.",
    scheduled_send_at: at,
    sent_at: status == "sent" ? at : nil
  )
end

acme = upsert_client(org, qbo, "acme", "Acme Studio", "ap@acme.test")
north = upsert_client(org, qbo, "north", "Northwind", "books@northwind.test")
globex = upsert_client(org, qbo, "globex", "Globex Corp", "payables@globex.test")
initech = upsert_client(org, qbo, "initech", "Initech", "ap@initech.test")
stark = upsert_client(org, qbo, "stark", "Stark Co", "finance@stark.test")
wayne = upsert_client(org, qbo, "wayne", "Wayne Ent", "ap@wayne.test")
umbrella = upsert_client(org, qbo, "umbrella", "Umbrella Labs", "ap@umbrella.test")
oscorp = upsert_client(org, qbo, "oscorp", "Oscorp", "billing@oscorp.test")
lex = upsert_client(org, qbo, "lex", "LexCorp", "ap@lexcorp.test")
tech = upsert_client(org, qbo, "tech", "TechCorp", "ap@techcorp.test")
voided = upsert_client(org, qbo, "void", "Harbor Media", "ap@harbor.test")

# Needs you — they wrote back with a date
inv = create_invoice(org, qbo, acme, number: "2041", due: today - 4, amount: 2400, chase: "needs_you", inbound_at: 8.hours.ago)
attach_thread(org, mailbox, inv, owner: owner, client_email: acme.primary_email, inbound: {
  at: 8.hours.ago,
  body: "Hi — payroll runs this Friday and we'll transfer the $2,400 then."
})

# Needs you — they wrote back about scope
inv = create_invoice(org, qbo, north, number: "2042", due: today - 2, amount: 1800, chase: "needs_you", inbound_at: 11.hours.ago)
attach_thread(org, mailbox, inv, owner: owner, client_email: north.primary_email, inbound: {
  at: 11.hours.ago,
  body: "We received invoice 2042 for $1,800 but the contracted scope was capped at $1,200. Can you check?"
})

# Needs you — date they named has passed
inv = create_invoice(org, qbo, globex, number: "2043", due: today - 10, amount: 4200, chase: "needs_you", expected: today - 3)
attach_thread(org, mailbox, inv, owner: owner, client_email: globex.primary_email, inbound: {
  at: 5.days.ago,
  body: "We'll clear this Friday — putting it on the pay run."
})
inv.invoice_chase_events.create!(event_type: "wait_expired", actor: "system", expected_pay_date: today - 3, created_at: Time.current)

# Needs you — Firm ready for your click
inv = create_invoice(org, qbo, initech, number: "2044", due: today - 12, amount: 5600, chase: "watching")
attach_thread(org, mailbox, inv, owner: owner, client_email: initech.primary_email)
queue_outbox(org, inv, step: "nudge_plus_3", status: "sent", at: 5.days.ago.change(hour: 10, min: 15))
queue_outbox(org, inv, step: "firm_plus_7", status: "draft", at: today.to_time.change(hour: 10, min: 15))

# Stopped — you killed the chase
inv = create_invoice(org, qbo, stark, number: "2085", due: today - 5, amount: 2500, chase: "stopped")
attach_thread(org, mailbox, inv, owner: owner, client_email: stark.primary_email)
inv.invoice_chase_events.create!(event_type: "stopped", actor: "user", created_at: Time.zone.local(2026, 9, 18, 10, 0))

# Watching — due-day reminder in 2 days
inv = create_invoice(org, qbo, wayne, number: "2081", due: today + 2, amount: 3100, chase: "watching")
attach_thread(org, mailbox, inv, owner: owner, client_email: wayne.primary_email)

# Watching — reminder 7 days after due is next (already past due-day)
inv = create_invoice(org, qbo, wayne, number: "2082", due: today - 3, amount: 900, chase: "watching")
attach_thread(org, mailbox, inv, owner: owner, client_email: wayne.primary_email)
queue_outbox(org, inv, step: "due_today", status: "sent", at: 3.days.ago.change(hour: 10, min: 15))

# Watching — on hold until a date they named
inv = create_invoice(org, qbo, umbrella, number: "2072", due: today - 8, amount: 5400, chase: "watching", expected: today + 5)
attach_thread(org, mailbox, inv, owner: owner, client_email: umbrella.primary_email, inbound: {
  at: 4.days.ago,
  body: "Can you hold until the 28th? Board meets then."
})
inv.update!(chase_status: "watching", expected_pay_date: today + 5)

# Watching — no thread
create_invoice(org, qbo, oscorp, number: "2060", due: today - 13, amount: 1750, chase: "watching")

# Watching — you stopped
inv = create_invoice(org, qbo, lex, number: "2055", due: today - 6, amount: 2200, chase: "stopped")
attach_thread(org, mailbox, inv, owner: owner, client_email: lex.primary_email)
inv.invoice_chase_events.create!(event_type: "stopped", actor: "user", created_at: 1.day.ago)

# Paid after due-day reminder
inv = create_invoice(org, qbo, tech, number: "2010", due: today - 20, amount: 1500, chase: "watching", books: "paid")
attach_thread(org, mailbox, inv, owner: owner, client_email: tech.primary_email)
queue_outbox(org, inv, step: "due_today", status: "sent", at: 18.days.ago.change(hour: 10, min: 15))
inv.invoice_chase_events.create!(event_type: "books_paid", actor: "system", created_at: 12.days.ago)

# Paid / voided
inv = create_invoice(org, qbo, voided, number: "2002", due: today - 30, amount: 800, chase: "watching", books: "voided")
attach_thread(org, mailbox, inv, owner: owner, client_email: voided.primary_email)
inv.invoice_chase_events.create!(event_type: "books_voided", actor: "system", created_at: 16.days.ago)

puts "Seeded chase demo for #{email} (#{org.invoices.where("external_id LIKE ?", "demo-%").count} demo invoices)."
