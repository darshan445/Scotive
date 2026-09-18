# frozen_string_literal: true

# Auth::ResetPassword Interactor
# Purpose: Set a new password from a Devise recoverable token.
# Methods:
# - execute

class Auth::ResetPassword
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(token:, password:, password_confirmation: nil)
    new(token: token, password: password, password_confirmation: password_confirmation).execute
  end

  def initialize(token:, password:, password_confirmation:)
    @token = token.to_s
    @password = password.to_s
    @password_confirmation = (password_confirmation.presence || password).to_s
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Reset token is required") if token.blank?
      raise_string_error("Password is required") if password.blank?
      raise_string_error("Password must be at least 8 characters") if password.length < 8
      raise_string_error("Passwords don't match") if password != password_confirmation

      user = User.reset_password_by_token(
        reset_password_token: token,
        password: password,
        password_confirmation: password_confirmation
      )

      if user.errors.any?
        raise_string_error(user.errors.full_messages.to_sentence.presence || "Reset token is invalid or has expired")
      end

      { message: "Your password has been reset." }
    end
  end

  private

  attr_reader :token, :password, :password_confirmation
end
