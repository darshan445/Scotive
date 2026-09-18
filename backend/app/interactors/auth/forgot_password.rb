# frozen_string_literal: true

# Auth::ForgotPassword Interactor
# Purpose: Issue a reset token and email the frontend link. Always succeeds for a valid email shape.
# Methods:
# - execute

class Auth::ForgotPassword
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(email:)
    new(email: email).execute
  end

  def initialize(email:)
    @email = email.to_s.strip.downcase
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Email is required") if email.blank?

      user = User.find_for_database_authentication(email: email)
      deliver_reset!(user) if user

      {
        message: "If an account exists for that email, a reset link is on its way."
      }
    end
  end

  private

  attr_reader :email

  def deliver_reset!(user)
    raw, hashed = Devise.token_generator.generate(User, :reset_password_token)
    user.reset_password_token = hashed
    user.reset_password_sent_at = Time.current
    user.save!(validate: false)
    AuthMailer.reset_password(user, raw).deliver_now
  end
end
