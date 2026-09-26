# frozen_string_literal: true

require "faraday"
require "securerandom"

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

  def get_email(email_id, account_id: nil)
    params = {}
    params[:account_id] = account_id if account_id.present?
    get("/api/v1/emails/#{email_id}", params)
  end

  def list_webhooks
    get("/api/v1/webhooks")
  end

  def create_webhook(payload)
    post("/api/v1/webhooks", payload)
  end

  def delete_webhook(webhook_id)
    response = connection.delete("/api/v1/webhooks/#{webhook_id}") do |req|
      req.headers["Accept"] = "application/json"
    end
    return if response.success? || response.status == 404

    raise Faraday::Error, "Unipile delete webhook failed (#{response.status}): #{response.body}"
  end

  def send_email(account_id:, to:, subject:, body:, cc: [], reply_to: nil, custom_headers: [], attachments: [])
    files = Array(attachments).compact
    if files.any?
      return post_multipart_email(
        account_id: account_id,
        to: to,
        subject: subject,
        body: body,
        cc: cc,
        reply_to: reply_to,
        custom_headers: custom_headers,
        attachments: files
      )
    end

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
    return response.body if response.success?

    raise Faraday::Error, format_error(context, response)
  end

  def format_error(context, response)
    parsed = response.body
    parsed = JSON.parse(parsed.to_s) if parsed.is_a?(String)
    parts = []
    if parsed.is_a?(Hash)
      parts << parsed["type"].presence
      parts << parsed["title"].presence
      parts << parsed["detail"].presence
      parts << parsed["message"].presence
    end
    detail = parts.compact.uniq.join(" — ").presence || parsed.inspect
    "#{context} failed (#{response.status}): #{detail}"
  rescue JSON::ParserError
    "#{context} failed (#{response.status}): #{response.body}"
  end

  def attendees(emails)
    Array(emails).filter_map do |email|
      identifier = email.to_s.strip
      next if identifier.blank?

      { identifier: identifier }
    end
  end

  def post_multipart_email(account_id:, to:, subject:, body:, cc:, reply_to:, custom_headers:, attachments:)
    boundary = "----Scotive#{SecureRandom.hex(8)}"
    chunks = []
    append_form_field(chunks, boundary, "account_id", account_id)
    append_form_field(chunks, boundary, "subject", subject.to_s)
    append_form_field(chunks, boundary, "body", body.to_s)
    append_form_field(chunks, boundary, "to", attendees(to).to_json)
    cc_list = attendees(cc)
    append_form_field(chunks, boundary, "cc", cc_list.to_json) if cc_list.any?
    append_form_field(chunks, boundary, "reply_to", reply_to) if reply_to.present?
    if Array(custom_headers).any?
      append_form_field(chunks, boundary, "custom_headers", Array(custom_headers).to_json)
    end
    Array(attachments).each do |file|
      filename = file[:filename].presence || file["filename"].presence || "attachment"
      content_type = file[:content_type].presence || file["content_type"].presence || "application/octet-stream"
      bytes = file[:content] || file["content"]
      next if bytes.nil? || bytes.bytesize.zero?

      chunks << "--#{boundary}\r\n"
      chunks << "Content-Disposition: form-data; name=\"attachments\"; filename=\"#{filename}\"\r\n"
      chunks << "Content-Type: #{content_type}\r\n\r\n"
      chunks << bytes
      chunks << "\r\n"
    end
    chunks << "--#{boundary}--\r\n"

    response = multipart_connection.post("/api/v1/emails") do |req|
      req.headers["Accept"] = "application/json"
      req.headers["Content-Type"] = "multipart/form-data; boundary=#{boundary}"
      req.body = chunks.map { |part| part.to_s.b }.join
    end
    unwrap!(response, "Unipile POST /api/v1/emails")
  end

  def append_form_field(chunks, boundary, name, value)
    chunks << "--#{boundary}\r\n"
    chunks << "Content-Disposition: form-data; name=\"#{name}\"\r\n\r\n"
    chunks << value.to_s
    chunks << "\r\n"
  end

  def multipart_connection
    Faraday.new(url: dsn) do |f|
      f.response :json, content_type: /\bjson$/
      f.headers["X-API-KEY"] = api_key
      f.options.timeout = 30
      f.adapter Faraday.default_adapter
    end
  end
end
