# frozen_string_literal: true

# Contacts::Create Interactor
# Purpose: public contact form (honeypot website field is silently accepted).
# Methods:
# - execute

class Contacts::Create
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(name:, email:, company:, message:, website: nil)
    new(name: name, email: email, company: company, message: message, website: website).execute
  end

  def initialize(name:, email:, company:, message:, website:)
    @name = name.to_s.strip.presence
    @email = email.to_s.strip
    @company = company.to_s.strip.presence
    @message = message.to_s.strip
    @website = website.to_s.strip
  end

  def execute
    execute_log_and_return_open_struct do
      if website.present?
        { accepted: true }
      else
        raise_string_error("Email is required") if email.blank?
        raise_string_error("Message is required") if message.blank?

        ContactMessage.create!(name: name, email: email, company: company, message: message)
        { accepted: true }
      end
    end
  end

  private

  attr_reader :name, :email, :company, :message, :website
end
