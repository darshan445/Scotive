# frozen_string_literal: true

require "faraday"

# Faraday wrapper for Unipile (Gmail + Outlook connection service).
class Email::EmailClient
  def create_hosted_auth_link(payload)
    post("/api/v1/hosted/accounts/link", payload)
  end

  def get_account(account_id)
    get("/api/v1/accounts/#{account_id}")
  end

  def list_emails(account_id:, after: nil, any_email: nil, search: nil, from: nil, folder: nil, cursor: nil, limit: 100)
    params = { account_id: account_id, limit: limit }
    params[:after] = after if after.present?
    params[:any_email] = any_email if any_email.present?
    params[:search] = search if search.present?
    params[:from] = from if from.present?
    params[:folder] = folder if folder.present?
    params[:cursor] = cursor if cursor.present?
    get("/api/v1/emails", params, timeout: 30)
  end

  def get_email(email_id)
    get("/api/v1/emails/#{email_id}")
  end

  def list_webhooks
    get("/api/v1/webhooks")
  end

  def create_webhook(payload)
    post("/api/v1/webhooks", payload)
  end

  def send_email(account_id:, to:, subject:, body:, cc: [], reply_to: nil, custom_headers: [])
    payload = {
      account_id: account_id,
      subject: subject,
      body: body,
      to: attendees(to)
    }
    payload[:cc] = attendees(cc) if Array(cc).compact.any?
    payload[:reply_to] = reply_to if reply_to.present?
    payload[:custom_headers] = custom_headers if Array(custom_headers).any?
    post("/api/v1/emails", payload)
  end

  def delete_account(account_id)
    response = connection.delete("/api/v1/accounts/#{account_id}") do |req|
      req.headers["Accept"] = "application/json"
    end
    return if response.success? || response.status == 404

    raise Faraday::Error, "Unipile delete account failed (#{response.status}): #{response.body}"
  end

  private

  def get(path, params = {}, timeout: nil)
    response = connection.get(path) do |req|
      req.headers["Accept"] = "application/json"
      params.each { |key, value| req.params[key] = value }
      req.options.timeout = timeout if timeout
    end
    unwrap!(response, "Unipile GET #{path}")
  end

  def post(path, payload)
    response = connection.post(path) do |req|
      req.headers["Accept"] = "application/json"
      req.headers["Content-Type"] = "application/json"
      req.body = payload
    end
    unwrap!(response, "Unipile POST #{path}")
  end

  def connection
    @connection ||= Faraday.new(url: dsn) do |f|
      f.request :json
      f.response :json, content_type: /\bjson$/
      f.headers["X-API-KEY"] = api_key
      f.options.timeout = 15
      f.adapter Faraday.default_adapter
    end
  end

  def dsn
    ENV.fetch("UNIPILE_DSN").to_s.chomp("/")
  end

  def api_key
    ENV.fetch("UNIPILE_API_KEY")
  end

  def unwrap!(response, context)
    unless response.success?
      raise Faraday::Error, "#{context} failed (#{response.status}): #{response.body}"
    end

    response.body
  end

  def attendees(emails)
    Array(emails).filter_map do |email|
      identifier = email.to_s.strip
      next if identifier.blank?

      { identifier: identifier }
    end
  end
end
