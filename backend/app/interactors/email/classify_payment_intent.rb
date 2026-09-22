# frozen_string_literal: true

# Email::ClassifyPaymentIntent Interactor
# Purpose: One orphan thread → invoice_payment / other_payment / unrelated. No invoice pick.
# Methods:
# - execute

class Email::ClassifyPaymentIntent
  include ExecuteMethodHelper
  include LogHelper

  PROMPT_PATH = Rails.root.join("prompts/payment_intent.txt")
  ALLOWED = %w[invoice_payment other_payment unrelated].freeze

  def self.execute(subject:, body:, client: Email::LlmClient.new)
    new(subject: subject, body: body, client: client).execute
  end

  def initialize(subject:, body:, client:)
    @subject = subject.to_s
    @body = body.to_s
    @client = client
  end

  def execute
    execute_log_and_return_open_struct do
      raw = client.complete_json(system: prompt, user: payload.to_json)
      raise_string_error("Payment intent returned invalid JSON") unless raw.is_a?(Hash)

      intent = raw.stringify_keys["intent"].to_s
      intent = "unrelated" unless ALLOWED.include?(intent)
      { intent: intent }
    end
  end

  private

  attr_reader :subject, :body, :client

  def payload
    { subject: subject, body: body.to_s.truncate(4000) }
  end

  def prompt
    File.read(PROMPT_PATH)
  end
end
