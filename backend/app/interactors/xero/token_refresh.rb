# frozen_string_literal: true

require "faraday"

# Shared Xero access-token refresh. Callers own Faraday → user-facing errors.
module Xero::TokenRefresh
  def ensure_fresh_token!(record)
    token = record.access_token
    if needs_token_refresh?(record)
      token = persist_refreshed_tokens!(record)
    end
    raise_string_error("Xero access token is missing") if token.blank?

    token
  rescue ActiveRecord::Encryption::Errors::Decryption
    mark_reauth!(record)
    raise_string_error("Xero credentials could not be decrypted — reconnect Xero")
  end

  def needs_token_refresh?(record)
    record.refresh_token.present? &&
      (record.token_expires_at.blank? || record.token_expires_at <= token_refresh_horizon)
  end

  def token_refresh_horizon
    10.minutes.from_now
  end

  def persist_refreshed_tokens!(record)
    tokens = client.refresh_access_token(refresh_token: record.refresh_token)
    token = tokens["access_token"] || tokens[:access_token]
    refresh = tokens["refresh_token"] || tokens[:refresh_token]
    expires_in = (tokens["expires_in"] || tokens[:expires_in]).to_i
    raise_string_error("Xero did not return an access token") if token.blank?

    record.update!(
      access_token: token,
      refresh_token: refresh.presence || record.refresh_token,
      token_expires_at: expires_in.positive? ? Time.current + expires_in.seconds : record.token_expires_at
    )
    token
  rescue Faraday::Error => e
    mark_reauth!(record) if xero_grant_error?(e)
    raise
  end

  def mark_reauth!(record)
    record.update!(connection_status: "reauth_required") if record.present?
  end

  def xero_grant_error?(error)
    error.message.to_s.match?(/invalid_grant|401|unauthorized/i)
  end
end
