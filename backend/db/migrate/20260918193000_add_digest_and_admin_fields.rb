# frozen_string_literal: true

class AddDigestAndAdminFields < ActiveRecord::Migration[8.1]
  def change
    add_column :organizations, :last_digest_sent_at, :datetime
    add_column :contact_messages, :status, :string, null: false, default: "new"
    add_index :contact_messages, :status
  end
end
