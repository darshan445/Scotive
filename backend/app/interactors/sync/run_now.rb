# frozen_string_literal: true

# Sync::RunNow Interactor
# Purpose: Run accounting, mailbox, and clock delta workers, then clear the running flag.
# Methods:
# - execute

class Sync::RunNow
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(organization:, qbo_client: Quickbooks::QuickbookClient.new, email_client: Email::EmailClient.new)
    new(organization: organization, qbo_client: qbo_client, email_client: email_client).execute
  end

  def initialize(organization:, qbo_client:, email_client:)
    @organization = organization
    @qbo_client = qbo_client
    @email_client = email_client
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Organization is required") if organization.blank?

      counts = empty_counts
      begin
        Webhooks::ReplayPending.execute(organization: organization)
        outcomes = run_workers
        counts = assemble(outcomes)
        Sync::State.store_counts!(organization.id, counts)
        counts
      ensure
        Sync::State.clear_running!(organization.id)
      end
    end
  end

  private

  attr_reader :organization, :qbo_client, :email_client

  def run_workers
    if Rails.env.test?
      sequential_workers
    else
      parallel_workers
    end
  end

  def sequential_workers
    {
      accounting: worker_result { Sync::AccountingDelta.execute(organization: organization, client: qbo_client) },
      mailbox: worker_result { Sync::MailboxDelta.execute(organization: organization, client: email_client) },
      clock: worker_result { Sync::ApplyClock.execute(organization: organization) }
    }
  end

  def parallel_workers
    jobs = {
      accounting: -> { worker_result { Sync::AccountingDelta.execute(organization: organization, client: qbo_client) } },
      mailbox: -> { worker_result { Sync::MailboxDelta.execute(organization: organization, client: email_client) } },
      clock: -> { worker_result { Sync::ApplyClock.execute(organization: organization) } }
    }
    threads = jobs.map do |name, work|
      Thread.new do
        Thread.current.report_on_exception = false
        ActiveRecord::Base.connection_pool.with_connection { [ name, work.call ] }
      end
    end
    threads.each_with_object({}) do |thread, memo|
      name, result = thread.value
      memo[name] = result
    end
  end

  def worker_result
    result = yield
    if result.success?
      { success: true, data: result.data }
    else
      { success: false, error: Array(result.errors).join(", ") }
    end
  rescue StandardError => e
    { success: false, error: e.message }
  end

  def assemble(outcomes)
    accounting = outcomes[:accounting][:data] || {}
    mailbox = outcomes[:mailbox][:data] || {}
    clock = outcomes[:clock][:data] || {}
    created = accounting[:created].to_i
    {
      accounting: accounting,
      mailbox: mailbox,
      clock: clock,
      qbo_cdc: { created: created },
      live_detected: created,
      skipped: created.positive? ? nil : mailbox[:skipped],
      errors: outcomes.each_with_object({}) do |(name, outcome), memo|
        memo[name] = outcome[:error] unless outcome[:success]
      end
    }
  end

  def empty_counts
    {
      accounting: {},
      mailbox: {},
      clock: {},
      qbo_cdc: { created: 0 },
      live_detected: 0,
      skipped: nil,
      errors: {}
    }
  end
end
