# frozen_string_literal: true

# Onboarding::BuildState Interactor
# Purpose: Derive the connect-screen phase from org integrations and mailbox match.
# Methods:
# - execute

class Onboarding::BuildState
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(organization:)
    new(organization: organization).execute
  end

  def initialize(organization:)
    @organization = organization
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Organization is required") if organization.blank?

      qbo = validate_result(Quickbooks::ConnectionStatus.execute(organization: organization)).data
      mail = validate_result(Email::ConnectionStatus.execute(organization: organization)).data
      imported = qbo[:last_invoice_import_at].present?
      matched = organization.integrations.mailbox.connected.where.not(sync_cursor: [ nil, "" ]).exists?
      phase = imported && mail[:connected] && matched ? "watching" : "connections"
      pipeline = matched ? { status: "complete", phase: "matching" } : nil

      {
        phase: phase,
        qbo_connected: qbo[:connected],
        gmail_connected: mail[:connected],
        last_invoice_import_at: qbo[:last_invoice_import_at],
        qbo_import_progress: qbo[:import_progress],
        qbo_pipeline: pipeline
      }
    end
  end

  private

  attr_reader :organization
end
