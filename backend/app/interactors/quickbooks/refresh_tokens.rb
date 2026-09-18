# frozen_string_literal: true

# Quickbooks::RefreshTokens Interactor
# Purpose: 6-hour poller — refresh QBO tokens expiring before the next run; invalid_grant → reauth.
# Methods:
# - execute

class Quickbooks::RefreshTokens
  include ExecuteMethodHelper
  include LogHelper
  include Quickbooks::TokenRefresh

  POLL_INTERVAL = 6.hours

  def self.execute(client: Quickbooks::QuickbookClient.new)
    new(client: client).execute
  end

  def initialize(client:)
    @client = client
  end

  def execute
    execute_log_and_return_open_struct do
      refreshed = 0
      reauth = 0
      skipped = 0
      Integration.accounting.connected.where(provider: "qbo").find_each do |record|
        outcome = refresh_one(record)
        case outcome
        when :refreshed then refreshed += 1
        when :reauth then reauth += 1
        else skipped += 1
        end
      end
      { refreshed: refreshed, reauth: reauth, skipped: skipped }
    end
  end

  private

  attr_reader :client

  def token_refresh_horizon
    POLL_INTERVAL.from_now
  end

  def refresh_one(record)
    if !needs_token_refresh?(record)
      :skipped
    else
      persist_refreshed_tokens!(record)
      :refreshed
    end
  rescue Faraday::Error => e
    qbo_grant_error?(e) ? :reauth : :failed
  end
end
