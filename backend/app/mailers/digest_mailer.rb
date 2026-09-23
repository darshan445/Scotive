# frozen_string_literal: true

class DigestMailer < ApplicationMailer
  default from: ENV.fetch("DEVISE_MAILER_SENDER", "scotive@localhost")

  SECTIONS = [
    [ :needs_you, "Needs you" ]
  ].freeze

  def daily(user:, groups:)
    @user = user
    @groups = groups
    @sections = SECTIONS.filter_map do |key, label|
      rows = Array(groups[key])
      next if rows.empty?

      { key: key, label: label, rows: rows }
    end
    @dashboard_url = "#{frontend_url}/dashboard"
    @frontend_url = frontend_url

    mail(to: user.email, subject: subject_line)
  end

  private

  def subject_line
    count = @sections.sum { |section| section[:rows].size }
    if count == 1
      "1 invoice needs you today"
    else
      "#{count} invoices need you today"
    end
  end

  def frontend_url
    ENV.fetch("FRONTEND_URL", "http://localhost:3001").to_s.chomp("/")
  end
end
