# frozen_string_literal: true

require "base64"
require "faraday"
require "uri"

# Faraday wrapper for Xero OAuth + Accounting GETs.
class Xero::XeroClient
  AUTHORIZE_HOST = "https://login.xero.com/identity/connect/authorize"
  IDENTITY_HOST = "https://identity.xero.com"
  API_ROOT = "https://api.xero.com"
  ACCOUNTING_PREFIX = "/api.xro/2.0"
  # offline_access is an OpenID identity scope. It is not listed on Configuration
  # (that page is accounting/payroll/files only). Request it in the authorize URL
  # or Xero issues a 30-minute access token and no refresh token.
  SCOPES = "offline_access accounting.settings accounting.contacts accounting.invoices"
  PAGE_SIZE = 100

  def authorization_url(state:, redirect_uri:)
    query = {
      response_type: "code",
      client_id: client_id,
      redirect_uri: redirect_uri,
      scope: SCOPES,
      state: state
    }
    "#{AUTHORIZE_HOST}?#{query.to_query}"
  end

  def exchange_code(code:, redirect_uri:)
    response = identity_connection.post("/connect/token") do |req|
      req.headers["Authorization"] = basic_auth_header
      req.headers["Accept"] = "application/json"
      req.body = {
        grant_type: "authorization_code",
        code: code,
        redirect_uri: redirect_uri
      }
    end
    unwrap!(response, "Xero token exchange")
  end

  def refresh_access_token(refresh_token:)
    response = identity_connection.post("/connect/token") do |req|
      req.headers["Authorization"] = basic_auth_header
      req.headers["Accept"] = "application/json"
      req.body = {
        grant_type: "refresh_token",
        refresh_token: refresh_token
      }
    end
    unwrap!(response, "Xero token refresh")
  end

  def list_connections(access_token:)
    response = root_connection.get("/connections") do |req|
      req.headers["Authorization"] = "Bearer #{access_token}"
      req.headers["Accept"] = "application/json"
    end
    body = unwrap!(response, "Xero connections")
    Array(body)
  end

  def delete_connection(access_token:, connection_id:)
    response = root_connection.delete("/connections/#{connection_id}") do |req|
      req.headers["Authorization"] = "Bearer #{access_token}"
      req.headers["Accept"] = "application/json"
    end
    return if response.success? || response.status == 404

    Rails.logger.warn("Xero connection delete failed (#{response.status}): #{response.body}")
  end

  def get_organisation(tenant_id:, access_token:)
    body = accounting_get("/Organisation", tenant_id: tenant_id, access_token: access_token, context: "Xero organisation")
    Array(body["Organisations"]).first || {}
  end

  def query_open_invoices(tenant_id:, access_token:, since_date:)
    since = Date.parse(since_date.to_s)
    paginate_invoices(
      tenant_id: tenant_id,
      access_token: access_token,
      where: 'Type=="ACCREC"',
      statuses: "AUTHORISED"
    ).select { |invoice| open_invoice_since?(invoice, since) }
  end

  def query_invoices_updated_since(tenant_id:, access_token:, since:)
    invoices = []
    page = 1
    loop do
      body = accounting_get(
        "/Invoices",
        tenant_id: tenant_id,
        access_token: access_token,
        context: "Xero invoice delta",
        params: { page: page, pageSize: PAGE_SIZE },
        headers: { "If-Modified-Since" => since.utc.httpdate }
      )
      page_rows = Array(body["Invoices"])
      invoices.concat(page_rows)
      break if page_rows.size < PAGE_SIZE

      page += 1
    end
    invoices
  end

  def query_contacts(tenant_id:, access_token:, ids:)
    ids.map { |id| id.to_s.strip }.uniq.select { |id| id.match?(/\A[\w-]+\z/) }.filter_map do |id|
      contact = get_contact(tenant_id: tenant_id, access_token: access_token, id: id)
      contact.presence
    end
  end

  def get_invoice(tenant_id:, access_token:, id:)
    body = accounting_get(
      "/Invoices/#{id}",
      tenant_id: tenant_id,
      access_token: access_token,
      context: "Xero invoice"
    )
    invoice = Array(body["Invoices"]).first
    raise Faraday::Error, "Xero invoice payload missing" if invoice.blank?

    invoice
  end

  def get_contact(tenant_id:, access_token:, id:)
    body = accounting_get(
      "/Contacts/#{id}",
      tenant_id: tenant_id,
      access_token: access_token,
      context: "Xero contact"
    )
    Array(body["Contacts"]).first || {}
  rescue Faraday::Error
    {}
  end

  def get_online_invoice_url(tenant_id:, access_token:, id:)
    body = accounting_get(
      "/Invoices/#{id}/OnlineInvoice",
      tenant_id: tenant_id,
      access_token: access_token,
      context: "Xero online invoice"
    )
    Array(body["OnlineInvoices"]).dig(0, "OnlineInvoiceUrl").presence
  rescue Faraday::Error
    nil
  end

  def revoke_token(token)
    response = Faraday.post("#{IDENTITY_HOST}/connect/revocation") do |req|
      req.headers["Authorization"] = basic_auth_header
      req.headers["Accept"] = "application/json"
      req.headers["Content-Type"] = "application/x-www-form-urlencoded"
      req.body = URI.encode_www_form(token: token)
      req.options.timeout = 15
    end
    return if response.success?

    Rails.logger.warn("Xero token revoke failed (#{response.status}): #{response.body}")
  end

  private

  def client_id
    ENV.fetch("XERO_CLIENT_ID")
  end

  def client_secret
    ENV.fetch("XERO_CLIENT_SECRET")
  end

  def basic_auth_header
    encoded = Base64.strict_encode64("#{client_id}:#{client_secret}")
    "Basic #{encoded}"
  end

  def paginate_invoices(tenant_id:, access_token:, where:, statuses: nil)
    invoices = []
    page = 1
    loop do
      params = { where: where, page: page, pageSize: PAGE_SIZE }
      params[:Statuses] = statuses if statuses.present?
      body = accounting_get(
        "/Invoices",
        tenant_id: tenant_id,
        access_token: access_token,
        context: "Xero open invoices",
        params: params
      )
      page_rows = Array(body["Invoices"])
      invoices.concat(page_rows)
      break if page_rows.size < PAGE_SIZE

      page += 1
    end
    invoices
  end

  def identity_connection
    @identity_connection ||= Faraday.new(url: IDENTITY_HOST) do |f|
      f.request :url_encoded
      f.response :json, content_type: /\bjson$/
      f.options.timeout = 15
      f.adapter Faraday.default_adapter
    end
  end

  def root_connection
    @root_connection ||= Faraday.new(url: API_ROOT) do |f|
      f.response :json, content_type: /\bjson$/
      f.options.timeout = 15
      f.adapter Faraday.default_adapter
    end
  end

  def accounting_connection
    @accounting_connection ||= Faraday.new(url: API_ROOT) do |f|
      f.response :json, content_type: /\bjson$/
      f.headers["User-Agent"] = "Scotive"
      f.options.timeout = 30
      f.adapter Faraday.default_adapter
    end
  end

  def open_invoice_since?(invoice, since)
    return false unless BigDecimal(invoice["AmountDue"].to_s) > 0

    issued = Xero::InvoiceMapper.parse_date(invoice["DateString"].presence || invoice["Date"])
    issued.blank? || issued >= since
  end

  def accounting_get(path, tenant_id:, access_token:, context:, params: {}, headers: {})
    response = accounting_connection.get("#{ACCOUNTING_PREFIX}#{path}") do |req|
      req.headers["Authorization"] = "Bearer #{access_token}"
      req.headers["Accept"] = "application/json"
      req.headers["Xero-tenant-id"] = tenant_id
      headers.each { |key, value| req.headers[key] = value }
      params.each { |key, value| req.params[key] = value }
    end
    unwrap!(response, context)
  end

  def unwrap!(response, context)
    unless response.success?
      raise Faraday::Error, "#{context} failed (#{response.status}): #{fault_text(response.body)}"
    end

    response.body
  end

  def fault_text(body)
    hash = body.is_a?(Hash) ? body : {}
    message = hash["Message"].presence || hash["Detail"].presence
    elements = Array(hash["Elements"]).filter_map { |row| row["ValidationErrors"] if row.is_a?(Hash) }.flatten
    first = elements.find { |row| row.is_a?(Hash) }
    validation = first.is_a?(Hash) ? first["Message"] : nil
    [ message, validation ].compact_blank.join(" — ").presence || body.to_s
  end
end
