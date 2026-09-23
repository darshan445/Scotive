# frozen_string_literal: true

class ApplicationController < ActionController::API
  include Devise::Controllers::Helpers

  private

  def current_organization
    current_user&.organization
  end

  def redirect_to_frontend(query)
    base = ENV.fetch("FRONTEND_URL", "http://localhost:3001").to_s.split(",").first.to_s.strip.chomp("/")
    qs = query.stringify_keys.compact_blank.to_query
    redirect_to "#{base}/dashboard?#{qs}", allow_other_host: true
  end
end
