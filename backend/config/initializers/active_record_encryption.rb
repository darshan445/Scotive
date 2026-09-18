# frozen_string_literal: true

# Tokens on integrations are encrypted at rest. Uses ENCRYPTION_KEY from .env
# (Unipile/QBO credentials never sit in plaintext columns).
Rails.application.configure do
  key = ENV["ENCRYPTION_KEY"].presence
  next unless key

  config.active_record.encryption.primary_key = key
  config.active_record.encryption.deterministic_key = key
  config.active_record.encryption.key_derivation_salt = key
end
