# frozen_string_literal: true

class CreateWebhookEventsAndOutboxMessages < ActiveRecord::Migration[8.1]
  def change
    create_table :webhook_events, id: :uuid do |t|
      t.references :organization, type: :uuid, foreign_key: true
      t.references :integration, type: :uuid, foreign_key: true
      t.string :provider, null: false
      t.string :external_event_id, null: false
      t.jsonb :payload, null: false
      t.string :status, null: false, default: "pending"
      t.text :error_message
      t.datetime :processed_at
      t.datetime :created_at, null: false
    end

    add_index :webhook_events, [ :provider, :external_event_id ],
              unique: true, name: "uq_webhook_provider_event"
    add_index :webhook_events, [ :status, :created_at ], name: "idx_webhook_pending",
              where: "status = 'pending'"

    create_table :outbox_messages, id: :uuid do |t|
      t.references :organization, type: :uuid, null: false, foreign_key: true
      t.references :invoice, type: :uuid, null: false, foreign_key: true
      t.references :conversation, type: :uuid, foreign_key: { on_delete: :nullify }
      t.string :status, null: false, default: "scheduled"
      t.string :to_address, null: false
      t.jsonb :cc_addresses, null: false, default: []
      t.text :subject, null: false
      t.text :body, null: false
      t.datetime :scheduled_send_at, null: false
      t.datetime :sent_at
      t.string :cancellation_reason
      t.timestamps
    end

    add_index :outbox_messages, [ :status, :scheduled_send_at ], name: "idx_outbox_queue",
              where: "status = 'scheduled'"
  end
end
