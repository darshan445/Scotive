# frozen_string_literal: true

require "rails_helper"

RSpec.describe Auth::DeleteAccount do
  let(:email) { "ada@agency.com" }
  let(:password) { "password1" }
  let!(:signup) { Auth::SignUp.execute(email: email, password: password, name: "Ada") }
  let(:token) { signup.data[:token] }
  let(:user) { User.find_by!(email: email) }
  let(:organization) { user.organization }
  let(:qbo_client) { instance_double(Quickbooks::QuickbookClient, revoke_token: nil) }
  let(:email_client) { instance_double(Email::EmailClient, delete_account: nil) }

  def execute!
    described_class.execute(
      user: user,
      confirm_email: email,
      token: token,
      qbo_client: qbo_client,
      email_client: email_client
    )
  end

  def create_mailbox!
    organization.integrations.create!(
      category: "mailbox",
      provider: "gmail",
      external_account_id: "acc-gmail",
      account_name: "ada@agency.com",
      connection_status: "connected"
    )
  end

  it "destroys the org even when webhook_events still point at the mailbox integration" do
    mailbox = create_mailbox!
    WebhookEvent.create!(
      organization: organization,
      integration: mailbox,
      provider: "gmail",
      external_event_id: "unipile:acc-gmail:mail_received:1",
      payload: { "event" => "mail_received" },
      created_at: Time.current
    )

    result = execute!
    expect(result.success?).to eq(true)
    expect(Organization.find_by(id: organization.id)).to be_nil
    expect(WebhookEvent.where(integration_id: mailbox.id)).to be_empty
    expect(JwtDenylist.exists?(jti: Warden::JWTAuth::TokenDecoder.new.call(token)["jti"])).to eq(true)
  end

  it "does not denylist the JWT when destroy fails" do
    create_mailbox!
    allow_any_instance_of(Organization).to receive(:destroy!).and_raise(ActiveRecord::RecordNotDestroyed.new("blocked"))

    result = execute!
    expect(result.success?).to eq(false)
    expect(User.find_by(email: email)).to be_present
    expect(JwtDenylist.count).to eq(0)
  end
end
