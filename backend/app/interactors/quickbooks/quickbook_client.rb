# frozen_string_literal: true

require "base64"
require "faraday"
require "uri"

# Faraday wrapper for Intuit OAuth + QBO Accounting GETs.
class Quickbooks::QuickbookClient
  OAUTH_HOST = "https://oauth.platform.intuit.com"
  AUTHORIZE_HOST = "https://appcenter.intuit.com/connect/oauth2"
  SANDBOX_API_HOST = "https://sandbox-quickbooks.api.intuit.com"
  PRODUCTION_API_HOST = "https://quickbooks.api.intuit.com"
  ACCOUNTING_SCOPE = "com.intuit.quickbooks.accounting"
  QUERY_PAGE_SIZE = 1000
  CUSTOMER_IN_BATCH = 20
  MINOR_VERSION = "75"

  def authorization_url(state:, redirect_uri:)
    query = {
      client_id: client_id,
      response_type: "code",
      scope: ACCOUNTING_SCOPE,
      redirect_uri: redirect_uri,
      state: state
    }
    "#{AUTHORIZE_HOST}?#{query.to_query}"
  end

  def exchange_code(code:, redirect_uri:)
    response = oauth_connection.post("/oauth2/v1/tokens/bearer") do |req|
      req.headers["Authorization"] = basic_auth_header
      req.headers["Accept"] = "application/json"
      req.body = {
        grant_type: "authorization_code",
        code: code,
        redirect_uri: redirect_uri
      }
    end
    unwrap!(response, "QBO token exchange")
  end

  def refresh_access_token(refresh_token:)
    response = oauth_connection.post("/oauth2/v1/tokens/bearer") do |req|
      req.headers["Authorization"] = basic_auth_header
      req.headers["Accept"] = "application/json"
      req.body = {
        grant_type: "refresh_token",
        refresh_token: refresh_token
      }
    end
    unwrap!(response, "QBO token refresh")
  end

  def get_company_info(realm_id:, access_token:)
    accounting_get(
      "/v3/company/#{realm_id}/companyinfo/#{realm_id}",
      access_token: access_token,
      context: "QBO company info"
    )
  end

  def query(realm_id:, access_token:, sql:)
    accounting_get(
      "/v3/company/#{realm_id}/query",
      access_token: access_token,
      context: "QBO query",
      params: { query: sql }
    )
  end

  def query_open_invoices(realm_id:, access_token:, since_date:)
    invoices = []
    start_position = 1
    loop do
      sql = "SELECT * FROM Invoice WHERE Balance > '0' AND TxnDate >= '#{since_date}' " \
            "STARTPOSITION #{start_position} MAXRESULTS #{QUERY_PAGE_SIZE}"
      page = entities(query(realm_id: realm_id, access_token: access_token, sql: sql), "Invoice")
      invoices.concat(page)
      break if page.size < QUERY_PAGE_SIZE

      start_position += QUERY_PAGE_SIZE
    end
    invoices
  end

  def query_invoices_updated_since(realm_id:, access_token:, since:)
    invoices = []
    start_position = 1
    stamp = since.utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    loop do
      sql = "SELECT * FROM Invoice WHERE MetaData.LastUpdatedTime > '#{stamp}' " \
            "STARTPOSITION #{start_position} MAXRESULTS #{QUERY_PAGE_SIZE}"
      page = entities(query(realm_id: realm_id, access_token: access_token, sql: sql), "Invoice")
      invoices.concat(page)
      break if page.size < QUERY_PAGE_SIZE

      start_position += QUERY_PAGE_SIZE
    end
    invoices
  end

  def query_customers(realm_id:, access_token:, ids:)
    ids.map { |id| id.to_s.strip }.uniq.select { |id| id.match?(/\A[\w-]+\z/) }.each_slice(CUSTOMER_IN_BATCH).flat_map do |slice|
      list = slice.map { |id| "'#{id}'" }.join(",")
      sql = "SELECT * FROM Customer WHERE Id IN (#{list})"
      entities(query(realm_id: realm_id, access_token: access_token, sql: sql), "Customer")
    end
  end

  def get_invoice(realm_id:, access_token:, id:)
    entity(accounting_get(
      "/v3/company/#{realm_id}/invoice/#{id}",
      access_token: access_token,
      context: "QBO invoice",
      params: { include: "invoiceLink" }
    ), "Invoice")
  end

  def get_payment(realm_id:, access_token:, id:)
    entity(accounting_get(
      "/v3/company/#{realm_id}/payment/#{id}",
      access_token: access_token,
      context: "QBO payment"
    ), "Payment")
  end

  def get_customer(realm_id:, access_token:, id:)
    entity(accounting_get(
      "/v3/company/#{realm_id}/customer/#{id}",
      access_token: access_token,
      context: "QBO customer"
    ), "Customer")
  end

  def revoke_token(token)
    response = Faraday.post("#{OAUTH_HOST}/oauth2/v1/tokens/revoke") do |req|
      req.headers["Authorization"] = basic_auth_header
      req.headers["Accept"] = "application/json"
      req.headers["Content-Type"] = "application/x-www-form-urlencoded"
      req.body = URI.encode_www_form(token: token)
      req.options.timeout = 15
    end
    return if response.success?

    Rails.logger.warn("QBO token revoke failed (#{response.status}): #{response.body}")
  end

  private

  def client_id
    ENV.fetch("QBO_CLIENT_ID")
  end

  def client_secret
    ENV.fetch("QBO_CLIENT_SECRET")
  end

  def basic_auth_header
    encoded = Base64.strict_encode64("#{client_id}:#{client_secret}")
    "Basic #{encoded}"
  end

  def production?
    ENV.fetch("QBO_ENV", "sandbox") == "production"
  end

  def oauth_connection
    @oauth_connection ||= Faraday.new(url: OAUTH_HOST) do |f|
      f.request :url_encoded
      f.response :json, content_type: /\bjson$/
      f.options.timeout = 15
      f.adapter Faraday.default_adapter
    end
  end

  def accounting_connection
    host = production? ? PRODUCTION_API_HOST : SANDBOX_API_HOST
    @accounting_connection ||= Faraday.new(url: host) do |f|
      f.response :json, content_type: /\bjson$/
      f.headers["User-Agent"] = "Scotive"
      f.options.timeout = 30
      f.adapter Faraday.default_adapter
    end
  end

  def accounting_get(path, access_token:, context:, params: {})
    response = accounting_connection.get(path) do |req|
      req.headers["Authorization"] = "Bearer #{access_token}"
      req.headers["Accept"] = "application/json"
      req.headers["Content-Type"] = "application/json"
      req.params["minorversion"] = MINOR_VERSION
      params.each { |key, value| req.params[key] = value }
    end
    unwrap!(response, context)
  end

  def entities(body, name)
    raw = body.is_a?(Hash) ? body.dig("QueryResponse", name) : nil
    return [] if raw.blank?

    raw.is_a?(Array) ? raw : [ raw ]
  end

  def entity(body, name)
    raw = body.is_a?(Hash) ? body[name] : nil
    raise Faraday::Error, "QBO #{name} payload missing" if raw.blank?

    raw
  end

  def unwrap!(response, context)
    unless response.success?
      raise Faraday::Error, "#{context} failed (#{response.status}): #{fault_text(response.body)}"
    end

    response.body
  end

  def fault_text(body)
    hash = body.is_a?(Hash) ? body : {}
    fault = hash["Fault"] || hash["fault"] || {}
    errors = fault["Error"] || fault["error"] || []
    first = errors.is_a?(Array) ? errors.first : errors
    if first.is_a?(Hash)
      [ first["Message"] || first["message"], first["Detail"] || first["detail"] ].compact_blank.join(" — ").presence || body.to_s
    else
      body.to_s
    end
  end
end
