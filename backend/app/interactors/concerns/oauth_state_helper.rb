# frozen_string_literal: true

module OauthStateHelper
  include LogHelper
  def encode_oauth_state(claims)
    Rails.application.message_verifier("oauth").generate(
      claims.deep_stringify_keys,
      expires_in: 15.minutes,
      purpose: :oauth
    )
  end

  def decode_oauth_state!(token)
    raise_string_error("Invalid or expired OAuth state") if token.blank?

    Rails.application.message_verifier("oauth").verify(token.to_s, purpose: :oauth)
  rescue ActiveSupport::MessageVerifier::InvalidSignature, ActiveSupport::MessageEncryptor::InvalidMessage
    raise_string_error("Invalid or expired OAuth state")
  end
end
