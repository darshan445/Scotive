# frozen_string_literal: true

# Auth::EncodeJwt Interactor
# Purpose: Issue a Devise JWT for an authenticated user.
# Methods:
# - execute

class Auth::EncodeJwt
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(user:)
    new(user: user).execute
  end

  def initialize(user:)
    @user = user
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("User is required") if user.blank?

      token, _payload = Warden::JWTAuth::UserEncoder.new.call(user, :user, nil)
      token
    end
  end

  private

  attr_reader :user
end
