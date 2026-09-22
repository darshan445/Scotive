# frozen_string_literal: true

module Simulate
  # Script-only QBO writes. Product QuickbookClient stays GET-only.
  class QboWriter < Quickbooks::QuickbookClient
    def access_token_for(integration)
      token = integration.access_token
      if integration.refresh_token.present? &&
          (integration.token_expires_at.blank? || integration.token_expires_at <= 10.minutes.from_now)
        tokens = refresh_access_token(refresh_token: integration.refresh_token)
        token = tokens["access_token"] || tokens[:access_token]
        refresh = tokens["refresh_token"] || tokens[:refresh_token]
        expires_in = (tokens["expires_in"] || tokens[:expires_in]).to_i
        raise "QuickBooks did not return an access token" if token.blank?

        integration.update!(
          access_token: token,
          refresh_token: refresh.presence || integration.refresh_token,
          token_expires_at: expires_in.positive? ? Time.current + expires_in.seconds : integration.token_expires_at
        )
      end
      raise "QuickBooks access token is missing" if token.blank?

      token
    end

    def find_or_create_customer(realm_id:, access_token:, email:, display_name:)
      found = query_customer_by_email(realm_id: realm_id, access_token: access_token, email: email)
      return found if found.present?

      body = accounting_post(
        "/v3/company/#{realm_id}/customer",
        access_token: access_token,
        context: "QBO create customer",
        payload: {
          "DisplayName" => display_name,
          "PrimaryEmailAddr" => { "Address" => email }
        }
      )
      entity(body, "Customer")
    rescue Faraday::Error => e
      if e.message.to_s.match?(/Duplicate|6240/i)
        query_customer_by_email(realm_id: realm_id, access_token: access_token, email: email) ||
          query_customer_by_name(realm_id: realm_id, access_token: access_token, name: display_name) ||
          raise
      else
        raise
      end
    end

    def create_invoice(realm_id:, access_token:, customer_id:, amount:, due_date:, issue_date:, email:, description:, doc_number: nil, item_id: nil, bcc_email: nil, customer_memo: nil)
      if doc_number.present?
        existing = query_invoice_by_number(realm_id: realm_id, access_token: access_token, doc_number: doc_number)
        return existing if existing.present? && BigDecimal(existing["Balance"].to_s).positive?
      end

      line_item_id = item_id.presence || default_item_id(realm_id: realm_id, access_token: access_token)
      payload = {
        "Line" => [
          {
            "Amount" => amount.to_f,
            "DetailType" => "SalesItemLineDetail",
            "Description" => description.to_s.presence || "Scotive AR simulation",
            "SalesItemLineDetail" => {
              "ItemRef" => { "value" => line_item_id.to_s },
              "Qty" => 1,
              "UnitPrice" => amount.to_f
            }
          }
        ],
        "CustomerRef" => { "value" => customer_id.to_s },
        "TxnDate" => issue_date.to_date.iso8601,
        "DueDate" => due_date.to_date.iso8601,
        "BillEmail" => { "Address" => email }
      }
      payload["DocNumber"] = doc_number.to_s if doc_number.present?
      payload["BillEmailBcc"] = { "Address" => bcc_email } if bcc_email.present?
      payload["CustomerMemo"] = { "value" => customer_memo.to_s.truncate(1000) } if customer_memo.present?

      body = accounting_post(
        "/v3/company/#{realm_id}/invoice",
        access_token: access_token,
        context: "QBO create invoice",
        payload: payload
      )
      created = entity(body, "Invoice")
      get_invoice(realm_id: realm_id, access_token: access_token, id: created["Id"])
    rescue Faraday::Error => e
      if bcc_email.present? && e.message.to_s.match?(/BillEmailBcc|Bcc/i)
        return create_invoice(
          realm_id: realm_id,
          access_token: access_token,
          customer_id: customer_id,
          amount: amount,
          due_date: due_date,
          issue_date: issue_date,
          email: email,
          description: description,
          doc_number: doc_number,
          item_id: item_id,
          bcc_email: nil,
          customer_memo: customer_memo
        )
      end
      if doc_number.present? && e.message.to_s.match?(/Duplicate|DocNumber/i)
        existing = query_invoice_by_number(realm_id: realm_id, access_token: access_token, doc_number: doc_number)
        return existing if existing.present?
      end
      raise
    end

    def apply_customer_memo!(realm_id:, access_token:, invoice:, memo:)
      return invoice if memo.blank?

      body = accounting_post(
        "/v3/company/#{realm_id}/invoice",
        access_token: access_token,
        context: "QBO invoice memo",
        payload: {
          "Id" => invoice["Id"].to_s,
          "SyncToken" => invoice["SyncToken"].to_s,
          "sparse" => true,
          "CustomerMemo" => { "value" => memo.to_s.truncate(1000) }
        }
      )
      entity(body, "Invoice")
    end

    def send_invoice(realm_id:, access_token:, invoice_id:, email: nil)
      path = "/v3/company/#{realm_id}/invoice/#{invoice_id}/send"
      params = {}
      params[:sendTo] = email if email.present?
      accounting_send(path, access_token: access_token, context: "QBO send invoice", params: params)
    end

    def invoice_for_email(realm_id:, access_token:, invoice_id:)
      entity(accounting_get(
        "/v3/company/#{realm_id}/invoice/#{invoice_id}",
        access_token: access_token,
        context: "QBO invoice + link",
        params: { include: "invoiceLink" }
      ), "Invoice")
    end

    def invoice_pdf(realm_id:, access_token:, invoice_id:)
      with_accounting_retry do
        host = production? ? PRODUCTION_API_HOST : SANDBOX_API_HOST
        conn = Faraday.new(url: host) do |f|
          f.options.timeout = 30
          f.adapter Faraday.default_adapter
        end
        response = conn.get("/v3/company/#{realm_id}/invoice/#{invoice_id}/pdf") do |req|
          req.headers["Authorization"] = "Bearer #{access_token}"
          req.headers["Accept"] = "application/pdf"
          req.params["minorversion"] = MINOR_VERSION
        end
        unless response.success?
          raise Faraday::Error, "QBO invoice PDF failed (#{response.status}): #{response.body.to_s.truncate(200)}"
        end

        response.body
      end
    end

    def company_name(realm_id:, access_token:)
      body = get_company_info(realm_id: realm_id, access_token: access_token)
      info = body.is_a?(Hash) ? (body["CompanyInfo"] || body) : {}
      info["CompanyName"].presence
    rescue Faraday::Error
      nil
    end

    def mark_email_sent!(realm_id:, access_token:, invoice:)
      entity(accounting_post(
        "/v3/company/#{realm_id}/invoice",
        access_token: access_token,
        context: "QBO EmailStatus EmailSent",
        payload: {
          "Id" => invoice["Id"].to_s,
          "SyncToken" => invoice["SyncToken"].to_s,
          "sparse" => true,
          "EmailStatus" => "EmailSent"
        }
      ), "Invoice")
    end

    private

    def query_customer_by_email(realm_id:, access_token:, email:)
      sql = "SELECT * FROM Customer WHERE PrimaryEmailAddr = '#{escape_sql(email)}'"
      entities(query(realm_id: realm_id, access_token: access_token, sql: sql), "Customer").first
    rescue Faraday::Error
      nil
    end

    def query_customer_by_name(realm_id:, access_token:, name:)
      sql = "SELECT * FROM Customer WHERE DisplayName = '#{escape_sql(name)}'"
      entities(query(realm_id: realm_id, access_token: access_token, sql: sql), "Customer").first
    rescue Faraday::Error
      nil
    end

    def query_invoice_by_number(realm_id:, access_token:, doc_number:)
      sql = "SELECT * FROM Invoice WHERE DocNumber = '#{escape_sql(doc_number)}'"
      entities(query(realm_id: realm_id, access_token: access_token, sql: sql), "Invoice").first
    rescue Faraday::Error
      nil
    end

    def default_item_id(realm_id:, access_token:)
      sql = "SELECT * FROM Item WHERE Active = true MAXRESULTS 20"
      rows = entities(query(realm_id: realm_id, access_token: access_token, sql: sql), "Item")
      service = rows.find { |row| row["Type"].to_s.casecmp("service").zero? }
      (service || rows.first)&.fetch("Id", nil).presence || "1"
    end

    def accounting_get(path, access_token:, context:, params: {})
      with_accounting_retry { super }
    end

    def accounting_post(path, access_token:, context:, payload:, params: {})
      with_accounting_retry do
        response = accounting_connection.post(path) do |req|
          req.headers["Authorization"] = "Bearer #{access_token}"
          req.headers["Accept"] = "application/json"
          req.headers["Content-Type"] = "application/json"
          req.params["minorversion"] = MINOR_VERSION
          params.each { |key, value| req.params[key] = value }
          req.body = payload.to_json
        end
        unwrap!(response, context)
      end
    end

    # /send is not an Invoice JSON body. `{}` makes Intuit demand DeliveryAddress.Address.
    def accounting_send(path, access_token:, context:, params: {})
      with_accounting_retry do
        response = accounting_connection.post(path) do |req|
          req.headers["Authorization"] = "Bearer #{access_token}"
          req.headers["Accept"] = "application/json"
          req.headers["Content-Type"] = "application/octet-stream"
          req.params["minorversion"] = MINOR_VERSION
          params.each { |key, value| req.params[key] = value }
          req.body = ""
        end
        unwrap!(response, context)
      end
    end

    def with_accounting_retry
      attempts = 0
      begin
        attempts += 1
        yield
      rescue Faraday::ConnectionFailed, Faraday::TimeoutError, SocketError, Errno::ECONNREFUSED => e
        raise if attempts >= 4 || !retryable_network?(e)

        @accounting_connection = nil
        sleep 2 * attempts
        retry
      end
    end

    def retryable_network?(error)
      error.message.to_s.match?(/getaddrinfo|Name or service not known|execution expired|Connection reset|Timed out|Failed to open TCP/i)
    end

    def escape_sql(value)
      value.to_s.gsub("'", "''")
    end
  end
end
