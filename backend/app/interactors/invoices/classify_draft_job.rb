# frozen_string_literal: true

# Invoices::ClassifyDraftJob Interactor
# Purpose: last inbound picks chase / facts / broken date / decision. No LLM.
# Methods:
# - execute

class Invoices::ClassifyDraftJob
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(invoice:)
    new(invoice: invoice).execute
  end

  def initialize(invoice:)
    @invoice = invoice
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Invoice is required") if invoice.blank?

      classify
    end
  end

  private

  attr_reader :invoice

  def classify
    if invoice.sleeping?
      { job: "decision", hold: true, reason: "Waiting until #{invoice.expected_pay_date}. Don't chase yet." }
    elsif silent? && !home_thread?
      { job: "decision", hold: true, reason: "No Gmail thread linked yet." }
    elsif silent?
      { job: "chase", hold: false, reason: "A payment reminder. Edit if you want it shorter or firmer." }
    elsif invoice.wait_expired?
      { job: "broken_date", hold: false, reason: "They named a date that passed." }
    else
      inbound_job
    end
  end

  def inbound_job
    text = last_body
    if file_or_form?(text)
      { job: "decision", hold: false, reason: "They asked for a file or form (W-9, PO, attachment)." }
    elsif paid_claim?(text)
      { job: "decision", hold: false, reason: "They say they already paid. Don't send a reminder." }
    elsif dispute_or_adjust?(text)
      { job: "decision", hold: false, reason: "They asked to change the amount or are disputing." }
    elsif facts_ask?(text)
      { job: "answer_facts", hold: false, reason: "They asked something we can answer from the invoice." }
    elsif promise?(text)
      { job: "decision", hold: false, reason: "They named when they'll pay. Pick a check-back — don't chase." }
    else
      { job: "decision", hold: false, reason: "They wrote back. Tell us what to send." }
    end
  end

  def silent?
    invoice.last_human_inbound_at.blank?
  end

  def home_thread?
    InvoiceConversation.where(invoice_id: invoice.id, is_primary: true).exists?
  end

  def last_body
    invoice.last_human_inbound_message&.clean_body.to_s
  end

  def file_or_form?(text)
    text.match?(/\b(w-?9|1099|tax form|purchase order|\bpo\b|attachment|resend|re-send)\b/i)
  end

  def paid_claim?(text)
    text.match?(/\b(already paid|we (already )?paid|we have paid|payment (was )?sent|wired|wire sent)\b/i)
  end

  def dispute_or_adjust?(text)
    text.match?(/\b(dispute|disputing|not (paying|owe)|on hold|legal)\b|\b(adjust|discount|credit|wrong amount|we agreed)|\b(take|cut|knock)\s+\$?\d/i)
  end

  def promise?(text)
    return true if text.match?(/\b(will pay|we'll pay|pay run|paying (on|next|friday)|scheduled)\b/i)

    inbound = invoice.last_human_inbound_message
    parsed = Email::ParseWaitDate.extract(text, as_of: inbound&.sent_at || Time.current)
    parsed.present?
  end

  def facts_ask?(text)
    text.match?(/\bhow (do|can) (i|we) pay\b|\b(payment link|wire instructions?|bank details)\b|\bwhat'?s? (the )?(balance|amount|due date)\b|\bwhen is (this|it|the invoice) due\b/i)
  end
end
