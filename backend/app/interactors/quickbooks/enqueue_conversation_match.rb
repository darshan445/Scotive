# frozen_string_literal: true

# Quickbooks::EnqueueConversationMatch Interactor
# Purpose: Run mailbox historical match after QBO import (AR Steps 2–3).
# Methods:
# - execute

class Quickbooks::EnqueueConversationMatch
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(organization:, client: Email::EmailClient.new)
    new(organization: organization, client: client).execute
  end

  def initialize(organization:, client:)
    @organization = organization
    @client = client
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Organization is required") if organization.blank?

      validate_result(Email::MatchOpenInvoices.execute(organization: organization, client: client)).data
    end
  end

  private

  attr_reader :organization, :client
end
