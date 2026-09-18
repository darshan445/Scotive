# frozen_string_literal: true

class AuthMailer < ApplicationMailer
  default from: ENV.fetch("DEVISE_MAILER_SENDER", "scotive@localhost")

  def reset_password(user, raw_token)
    @user = user
    @reset_url = "#{frontend_url}/reset-password?token=#{CGI.escape(raw_token)}"

    mail(to: user.email, subject: "Reset your Scotive password")
  end

  private

  def frontend_url
    ENV.fetch("FRONTEND_URL", "http://localhost:3001").to_s.chomp("/")
  end
end
