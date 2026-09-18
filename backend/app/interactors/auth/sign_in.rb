# frozen_string_literal: true

# Auth::SignIn Interactor
# Purpose: Authenticate email/password and return a session payload.
# Methods:
# - execute

class Auth::SignIn
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(email:, password:, request: nil)
    new(email: email, password: password, request: request).execute
  end

  def initialize(email:, password:, request:)
    @email = email.to_s.strip.downcase
    @password = password.to_s
    @request = request
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Invalid email or password") if email.blank? || password.blank?

      user = User.find_for_database_authentication(email: email)
      raise_string_error("Invalid email or password") unless user&.valid_password?(password)

      user.update_tracked_fields!(request) if request.present?

      token = validate_result(Auth::EncodeJwt.execute(user: user)).data
      validate_result(Auth::SessionPayload.execute(user: user.reload, token: token)).data
    end
  end

  private

  attr_reader :email, :password, :request
end
