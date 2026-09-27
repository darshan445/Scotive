# frozen_string_literal: true

require "rails_helper"

RSpec.describe Xero::XeroClient do
  describe "#query_open_invoices" do
    it "GETs /api.xro/2.0/Invoices with Type and AUTHORISED filters" do
      client = described_class.new
      connection = instance_double(Faraday::Connection)
      request = instance_double(Faraday::Request)
      allow(request).to receive(:headers).and_return({})
      allow(request).to receive(:params).and_return({})
      allow(client).to receive(:accounting_connection).and_return(connection)
      expect(connection).to receive(:get).with("/api.xro/2.0/Invoices") do |&block|
        block.call(request)
        instance_double(
          Faraday::Response,
          success?: true,
          body: {
            "Invoices" => [
              {
                "InvoiceID" => "inv-1",
                "Type" => "ACCREC",
                "Status" => "AUTHORISED",
                "AmountDue" => "40.00",
                "DateString" => 10.days.ago.to_date.iso8601
              },
              {
                "InvoiceID" => "inv-old",
                "Type" => "ACCREC",
                "Status" => "AUTHORISED",
                "AmountDue" => "40.00",
                "DateString" => 400.days.ago.to_date.iso8601
              },
              {
                "InvoiceID" => "inv-paid",
                "Type" => "ACCREC",
                "Status" => "AUTHORISED",
                "AmountDue" => "0.00",
                "DateString" => 10.days.ago.to_date.iso8601
              }
            ]
          }
        )
      end

      rows = client.query_open_invoices(
        tenant_id: "tenant-1",
        access_token: "at",
        since_date: 365.days.ago.to_date.iso8601
      )

      expect(rows.map { |row| row["InvoiceID"] }).to eq([ "inv-1" ])
      expect(request.params[:where]).to eq('Type=="ACCREC"')
      expect(request.params[:Statuses]).to eq("AUTHORISED")
    end
  end
end
