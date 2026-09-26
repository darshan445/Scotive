# frozen_string_literal: true

# Invoices::SendChase Interactor
# Purpose: user-approved send on the last client thread. Requires a check-back date so a ghost returns to Needs you.
# Methods:
# - execute

class Invoices::SendChase
  include ExecuteMethodHelper
  include LogHelper
  include Cadence::HomeThreadSend

  MAX_ATTACHMENT_BYTES = 25.megabytes
  MAX_ATTACHMENTS = 10
  BLOCKED_ATTACHMENT = /\.(exe|bat|cmd|com|scr|js|vbs|msi|dll)\z/i

  def self.execute(organization:, invoice_id:, subject:, body:, wait_until: nil, include_pay_link: nil, attachments: [], client: Email::EmailClient.new)
    new(
      organization: organization,
      invoice_id: invoice_id,
      subject: subject,
      body: body,
      wait_until: wait_until,
      include_pay_link: include_pay_link,
      attachments: attachments,
      client: client
    ).execute
  end

  def initialize(organization:, invoice_id:, subject:, body:, wait_until:, include_pay_link:, attachments:, client:)
    @organization = organization
    @invoice_id = invoice_id
    @subject = subject.to_s.strip
    @body = body.to_s.strip
    @wait_until = wait_until
    @include_pay_link = include_pay_link
    @attachments = Array(attachments)
    @client = client
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Organization is required") if organization.blank?
      raise_string_error("Subject is required") if subject.blank?
      raise_string_error("Body is required") if body.blank?

      outcome = nil
      Invoice.transaction do
        invoice = organization.invoices.lock.find_by(id: invoice_id)
        raise_string_error("Invoice not found") if invoice.blank?
        raise_string_error("This invoice is paid") if invoice.books_closed?
        raise_string_error("Client email is missing") if invoice.client&.primary_email.blank?
        raise_string_error("Check-back date is required") if parsed_wait.blank?
        raise_string_error("Check-back date must be today or later") if parsed_wait < organization.today
        files = normalized_attachments
        raise_string_error("Too many attachments (max #{MAX_ATTACHMENTS})") if files.length > MAX_ATTACHMENTS
        raise_string_error("Attachments must be under 25 MB total") if files.sum { |file| file[:content].bytesize } > MAX_ATTACHMENT_BYTES

        draft = invoice.outbox_messages.where(status: "draft").order(created_at: :desc).first
        conversation = reply_thread_for(invoice, draft)
        raise_string_error("Home thread is missing") if conversation.blank?

        outcome = deliver_home_thread!(
          invoice: invoice,
          to: reply_address_for(invoice, conversation),
          cc: Array(invoice.cc_emails),
          subject: threaded_subject(conversation, subject),
          body: body,
          client: client,
          outbox: draft,
          conversation: conversation,
          include_pay_link: parsed_include_pay_link,
          attachments: files
        )
        invoice.outbox_messages.where(status: "scheduled").find_each do |row|
          row.update!(status: "cancelled", cancellation_reason: "human_sent")
        end
        apply_wait_until!(invoice, parsed_wait)
        outcome[:invoice] = Ledger::InvoicePayload.for(invoice.reload)
      end
      outcome
    end
  end

  private

  attr_reader :organization, :invoice_id, :subject, :body, :wait_until, :include_pay_link, :attachments, :client

  def parsed_include_pay_link
    return if include_pay_link.nil?

    include_pay_link == true || include_pay_link.to_s == "true"
  end

  def normalized_attachments
    attachments.filter_map do |file|
      next if file.blank?

      if file.respond_to?(:original_filename)
        name = file.original_filename.to_s
        bytes = file.read
        type = file.content_type
      else
        name = (file[:filename] || file["filename"]).to_s
        bytes = file[:content] || file["content"]
        type = file[:content_type] || file["content_type"]
      end
      next if name.blank? || bytes.blank?
      raise_string_error("#{name} is not allowed") if name.match?(BLOCKED_ATTACHMENT)

      { filename: name, content_type: type.presence || "application/octet-stream", content: bytes }
    end
  end

  def parsed_wait
    return if wait_until.blank?
    return wait_until.to_date if wait_until.respond_to?(:to_date) && !wait_until.is_a?(String)

    Date.parse(wait_until.to_s)
  rescue Date::Error, ArgumentError
    nil
  end
end
