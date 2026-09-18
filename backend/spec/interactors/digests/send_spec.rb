# frozen_string_literal: true

require "rails_helper"

RSpec.describe Digests::Send do
  include ActiveSupport::Testing::TimeHelpers

  let(:organization) { Organization.create!(name: "Ada's workspace", daily_digest_enabled: true, daily_digest_hour: 9) }
  let!(:owner) do
    User.create!(
      organization: organization,
      email: "ada@agency.com",
      password: "password1",
      password_confirmation: "password1",
      first_name: "Ada",
      role: "owner"
    )
  end
  let!(:qbo) do
    organization.integrations.create!(
      category: "accounting",
      provider: "qbo",
      external_account_id: "realm-1",
      account_name: "Studio",
      connection_status: "connected"
    )
  end
  let(:client_row) do
    organization.clients.create!(
      integration: qbo,
      external_id: "1",
      name: "Acme",
      primary_email: "ap@acme.com"
    )
  end

  def create_overdue!
    organization.invoices.create!(
      integration: qbo,
      client: client_row,
      external_id: "INV-OD",
      invoice_number: "INV-OD",
      issue_date: Date.new(2026, 8, 1),
      due_date: Date.new(2026, 9, 1),
      total_amount: 100,
      balance_remaining: 100,
      current_ar_status: "overdue"
    )
  end

  it "emails owners at the saved local hour and records last_digest_sent_at" do
    create_overdue!
    travel_to Time.utc(2026, 9, 18, 9, 5) do
      expect { described_class.execute }.to change { ActionMailer::Base.deliveries.size }.by(1)
      mail = ActionMailer::Base.deliveries.last
      expect(mail.to).to eq([ "ada@agency.com" ])
      expect(mail.subject).to eq("1 invoice needs you today")
      expect(mail.body.encoded).to include("INV-OD")
      expect(organization.reload.last_digest_sent_at).to be_present
    end
  end

  it "skips when it is not the saved hour" do
    create_overdue!
    travel_to Time.utc(2026, 9, 18, 12, 0) do
      expect { described_class.execute }.not_to change { ActionMailer::Base.deliveries.size }
    end
  end

  it "skips an empty digest and does not mark sent" do
    travel_to Time.utc(2026, 9, 18, 9, 5) do
      expect { described_class.execute }.not_to change { ActionMailer::Base.deliveries.size }
      expect(organization.reload.last_digest_sent_at).to be_nil
    end
  end

  it "does not send twice in the same local day" do
    create_overdue!
    travel_to Time.utc(2026, 9, 18, 9, 5) do
      described_class.execute
      expect { described_class.execute }.not_to change { ActionMailer::Base.deliveries.size }
    end
  end

  it "uses the organization timezone for the send window" do
    organization.update!(time_zone: "America/New_York", daily_digest_hour: 7)
    create_overdue!
    travel_to Time.utc(2026, 9, 18, 11, 5) do
      expect { described_class.execute }.to change { ActionMailer::Base.deliveries.size }.by(1)
    end
  end
end
