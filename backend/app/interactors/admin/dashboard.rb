# frozen_string_literal: true

# Admin::Dashboard Interactor
# Purpose: ops snapshot of users, mailbox/QBO connections, and invoice counts.
# Methods:
# - execute

class Admin::Dashboard
  include ExecuteMethodHelper
  include LogHelper

  def self.execute
    new.execute
  end

  def execute
    execute_log_and_return_open_struct do
      users = User.includes(organization: :integrations).order(created_at: :desc)
      rows = users.map { |user| user_row(user) }
      {
        stats: stats_for(rows),
        users: rows
      }
    end
  end

  private

  def user_row(user)
    organization = user.organization
    mailbox = organization.integrations.find { |row| row.mailbox? && row.connected? }
    qbo = organization.integrations.find { |row| row.provider == "qbo" && row.connected? }
    xero = organization.integrations.find { |row| row.provider == "xero" && row.connected? }
    {
      id: user.id,
      email: user.email,
      name: user.full_name,
      created_at: user.created_at&.iso8601,
      gmail_connected: mailbox.present?,
      mailbox_provider: mailbox&.provider,
      gmail_email: mailbox&.account_name.presence || mailbox&.external_account_id,
      qbo_connected: qbo.present?,
      qbo_company: qbo&.account_name,
      xero_connected: xero.present?,
      xero_company: xero&.account_name,
      invoice_count: invoice_counts[organization.id] || 0,
      open_invoice_count: open_invoice_counts[organization.id] || 0
    }
  end

  def stats_for(rows)
    {
      total_users: rows.size,
      gmail_connected: rows.count { |row| row[:gmail_connected] },
      qbo_connected: rows.count { |row| row[:qbo_connected] },
      both_connected: rows.count { |row| row[:gmail_connected] && row[:qbo_connected] },
      neither_connected: rows.count { |row| !row[:gmail_connected] && !row[:qbo_connected] },
      total_invoices: invoice_counts.values.sum
    }
  end

  def invoice_counts
    @invoice_counts ||= Invoice.group(:organization_id).count
  end

  def open_invoice_counts
    @open_invoice_counts ||= Invoice.books_open.group(:organization_id).count
  end
end
