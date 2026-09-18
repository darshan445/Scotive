# frozen_string_literal: true

# Auth::SignOut Interactor
# Purpose: Revoke the current JWT so it cannot be reused.
# Methods:
# - execute

class Auth::SignOut
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(token:, user: nil)
    new(token: token, user: user).execute
  end

  def initialize(token:, user:)
    @token = token.to_s.delete_prefix("Bearer ").strip
    @user = user
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Missing access token") if token.blank?

      payload = Warden::JWTAuth::TokenDecoder.new.call(token)
      JwtDenylist.revoke_jwt(payload, user)
      true
    end
  end

  private

  attr_reader :token, :user
end
