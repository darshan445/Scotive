# frozen_string_literal: true

require "sidekiq/web"
require "sidekiq/cron/web"

# Sidekiq::Web is its own Rack app. API-only Rails does not share sessions with it.
Sidekiq::Web.use ActionDispatch::Cookies
Sidekiq::Web.use ActionDispatch::Session::CookieStore, Rails.application.config.session_options

unless Rails.env.local?
  Sidekiq::Web.use Rack::Auth::Basic, "Sidekiq" do |username, password|
    expected_user = ENV["SIDEKIQ_WEB_USERNAME"].to_s
    expected_pass = ENV["SIDEKIQ_WEB_PASSWORD"].to_s
    next false if expected_user.blank? || expected_pass.blank?

    ActiveSupport::SecurityUtils.secure_compare(
      Digest::SHA256.hexdigest(username),
      Digest::SHA256.hexdigest(expected_user)
    ) & ActiveSupport::SecurityUtils.secure_compare(
      Digest::SHA256.hexdigest(password),
      Digest::SHA256.hexdigest(expected_pass)
    )
  end
end
