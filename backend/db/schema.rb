# This file is auto-generated from the current state of the database. Instead
# of editing this file, please use the migrations feature of Active Record to
# incrementally modify your database, and then regenerate this schema definition.
#
# This file is the source Rails uses to define your schema when running `bin/rails
# db:schema:load`. When creating a new database, `bin/rails db:schema:load` tends to
# be faster and is potentially less error prone than running all of your
# migrations from scratch. Old migrations may fail to apply correctly if those
# migrations use external dependencies or application code.
#
# It's strongly recommended that you check this file into your version control system.

ActiveRecord::Schema[8.1].define(version: 2026_09_18_190500) do
  # These are extensions that must be enabled in order to support this database
  enable_extension "pg_catalog.plpgsql"
  enable_extension "pgcrypto"

  create_table "clients", id: :uuid, default: -> { "gen_random_uuid()" }, force: :cascade do |t|
    t.jsonb "associated_emails", default: [], null: false
    t.datetime "created_at", null: false
    t.string "domain"
    t.string "external_id", null: false
    t.uuid "integration_id", null: false
    t.string "name", null: false
    t.uuid "organization_id", null: false
    t.string "primary_email"
    t.datetime "updated_at", null: false
    t.index ["integration_id", "external_id"], name: "uq_clients_integration_external", unique: true
    t.index ["integration_id"], name: "index_clients_on_integration_id"
    t.index ["organization_id", "domain"], name: "idx_clients_domain"
    t.index ["organization_id", "primary_email"], name: "idx_clients_primary_email"
    t.index ["organization_id"], name: "index_clients_on_organization_id"
  end

  create_table "contact_messages", id: :uuid, default: -> { "gen_random_uuid()" }, force: :cascade do |t|
    t.string "company"
    t.datetime "created_at", null: false
    t.string "email", null: false
    t.text "message", null: false
    t.string "name"
    t.datetime "updated_at", null: false
  end

  create_table "conversations", id: :uuid, default: -> { "gen_random_uuid()" }, force: :cascade do |t|
    t.datetime "created_at", null: false
    t.string "external_thread_id", null: false
    t.uuid "integration_id", null: false
    t.uuid "organization_id", null: false
    t.string "status", default: "active", null: false
    t.text "subject"
    t.datetime "updated_at", null: false
    t.index ["integration_id", "external_thread_id"], name: "uq_conversations_integration_thread", unique: true
    t.index ["integration_id"], name: "index_conversations_on_integration_id"
    t.index ["organization_id"], name: "index_conversations_on_organization_id"
  end

  create_table "integrations", id: :uuid, default: -> { "gen_random_uuid()" }, force: :cascade do |t|
    t.text "access_token"
    t.string "account_name"
    t.string "category", null: false
    t.string "connection_status", default: "connected", null: false
    t.datetime "created_at", null: false
    t.string "external_account_id"
    t.datetime "last_synced_at"
    t.uuid "organization_id", null: false
    t.string "provider", null: false
    t.text "refresh_token"
    t.string "sync_cursor"
    t.datetime "token_expires_at"
    t.datetime "updated_at", null: false
    t.datetime "webhook_expires_at"
    t.string "webhook_subscription_id"
    t.index ["organization_id", "category", "connection_status"], name: "idx_integrations_active"
    t.index ["organization_id", "provider", "external_account_id"], name: "uq_integrations_org_provider_account", unique: true
    t.index ["organization_id"], name: "index_integrations_on_organization_id"
  end

  create_table "invoice_conversations", primary_key: ["invoice_id", "conversation_id"], force: :cascade do |t|
    t.uuid "conversation_id", null: false
    t.datetime "created_at", null: false
    t.uuid "invoice_id", null: false
    t.boolean "is_primary", default: false, null: false
    t.index ["conversation_id"], name: "idx_invoice_conversations_conv"
  end

  create_table "invoice_events", id: :uuid, default: -> { "gen_random_uuid()" }, force: :cascade do |t|
    t.decimal "confidence", precision: 3, scale: 2
    t.datetime "created_at", null: false
    t.jsonb "event_data", default: {}, null: false
    t.string "event_type", null: false
    t.uuid "invoice_id", null: false
    t.uuid "message_id"
    t.text "quote"
    t.string "sender", null: false
    t.index ["invoice_id", "created_at"], name: "idx_invoice_events_invoice"
    t.index ["invoice_id"], name: "index_invoice_events_on_invoice_id"
  end

  create_table "invoice_state_transitions", id: :uuid, default: -> { "gen_random_uuid()" }, force: :cascade do |t|
    t.datetime "created_at", null: false
    t.decimal "disputed_amount", precision: 12, scale: 2
    t.string "from_status"
    t.uuid "invoice_id", null: false
    t.boolean "is_reverted", default: false, null: false
    t.boolean "needs_reply", default: false, null: false
    t.date "promise_date"
    t.text "reason_quote"
    t.string "to_status", null: false
    t.string "trigger_source", null: false
    t.uuid "triggered_by_message_id"
    t.index ["invoice_id", "created_at"], name: "idx_state_transitions_audit", order: { created_at: :desc }
    t.index ["invoice_id"], name: "index_invoice_state_transitions_on_invoice_id"
  end

  create_table "invoices", id: :uuid, default: -> { "gen_random_uuid()" }, force: :cascade do |t|
    t.date "active_promise_date"
    t.decimal "balance_remaining", precision: 12, scale: 2, null: false
    t.jsonb "bcc_emails", default: [], null: false
    t.jsonb "cc_emails", default: [], null: false
    t.uuid "client_id", null: false
    t.datetime "created_at", null: false
    t.string "currency", default: "USD", null: false
    t.string "current_ar_status", default: "invoiced", null: false
    t.decimal "disputed_claim_amount", precision: 12, scale: 2
    t.date "due_date", null: false
    t.string "external_id", null: false
    t.uuid "integration_id", null: false
    t.string "invoice_number", null: false
    t.date "issue_date", null: false
    t.boolean "needs_reply", default: false, null: false
    t.uuid "organization_id", null: false
    t.string "pay_link_token"
    t.datetime "snoozed_until"
    t.decimal "total_amount", precision: 12, scale: 2, null: false
    t.datetime "updated_at", null: false
    t.index ["client_id"], name: "index_invoices_on_client_id"
    t.index ["integration_id", "external_id"], name: "uq_invoices_integration_external", unique: true
    t.index ["integration_id"], name: "index_invoices_on_integration_id"
    t.index ["organization_id", "current_ar_status", "due_date"], name: "idx_invoices_status_dates"
    t.index ["organization_id", "invoice_number"], name: "idx_invoices_number"
    t.index ["organization_id", "pay_link_token"], name: "idx_invoices_token", where: "(pay_link_token IS NOT NULL)"
    t.index ["organization_id"], name: "index_invoices_on_organization_id"
  end

  create_table "jwt_denylists", id: :uuid, default: -> { "gen_random_uuid()" }, force: :cascade do |t|
    t.datetime "created_at", null: false
    t.datetime "exp", null: false
    t.string "jti", null: false
    t.datetime "updated_at", null: false
    t.index ["jti"], name: "index_jwt_denylists_on_jti", unique: true
  end

  create_table "messages", id: :uuid, default: -> { "gen_random_uuid()" }, force: :cascade do |t|
    t.jsonb "cc_addresses", default: [], null: false
    t.text "clean_body"
    t.uuid "conversation_id", null: false
    t.datetime "created_at", null: false
    t.string "direction", null: false
    t.string "external_message_id", null: false
    t.string "from_address", null: false
    t.boolean "is_anchor", default: false, null: false
    t.boolean "processed_by_ai", default: false, null: false
    t.datetime "sent_at", null: false
    t.jsonb "to_addresses", default: [], null: false
    t.index ["conversation_id", "external_message_id"], name: "uq_messages_conversation_ext_id", unique: true
    t.index ["conversation_id", "sent_at"], name: "idx_messages_sent_at"
    t.index ["conversation_id"], name: "index_messages_on_conversation_id"
  end

  create_table "organizations", id: :uuid, default: -> { "gen_random_uuid()" }, force: :cascade do |t|
    t.datetime "created_at", null: false
    t.boolean "daily_digest_enabled", default: false, null: false
    t.integer "daily_digest_hour", default: 9, null: false
    t.jsonb "escalation_offsets", default: [-3, 0, 7, 9], null: false
    t.integer "follow_up_interval_days", default: 3, null: false
    t.boolean "friendly_auto_send", default: true, null: false
    t.string "name", null: false
    t.string "time_zone", default: "UTC", null: false
    t.datetime "updated_at", null: false
  end

  create_table "outbox_messages", id: :uuid, default: -> { "gen_random_uuid()" }, force: :cascade do |t|
    t.text "body", null: false
    t.string "cadence_step"
    t.string "cancellation_reason"
    t.jsonb "cc_addresses", default: [], null: false
    t.uuid "conversation_id"
    t.datetime "created_at", null: false
    t.uuid "invoice_id", null: false
    t.uuid "organization_id", null: false
    t.datetime "scheduled_send_at", null: false
    t.datetime "sent_at"
    t.string "status", default: "scheduled", null: false
    t.text "subject", null: false
    t.string "to_address", null: false
    t.datetime "updated_at", null: false
    t.index ["conversation_id"], name: "index_outbox_messages_on_conversation_id"
    t.index ["invoice_id", "cadence_step"], name: "uq_outbox_pending_step", unique: true, where: "(((status)::text = ANY (ARRAY[('scheduled'::character varying)::text, ('draft'::character varying)::text])) AND (cadence_step IS NOT NULL))"
    t.index ["invoice_id"], name: "index_outbox_messages_on_invoice_id"
    t.index ["organization_id"], name: "index_outbox_messages_on_organization_id"
    t.index ["status", "scheduled_send_at"], name: "idx_outbox_queue", where: "((status)::text = 'scheduled'::text)"
  end

  create_table "users", id: :uuid, default: -> { "gen_random_uuid()" }, force: :cascade do |t|
    t.datetime "created_at", null: false
    t.datetime "current_sign_in_at"
    t.string "current_sign_in_ip"
    t.string "email", default: "", null: false
    t.string "encrypted_password", default: "", null: false
    t.string "first_name"
    t.string "last_name"
    t.datetime "last_sign_in_at"
    t.string "last_sign_in_ip"
    t.uuid "organization_id", null: false
    t.datetime "remember_created_at"
    t.datetime "reset_password_sent_at"
    t.string "reset_password_token"
    t.string "role", default: "member", null: false
    t.integer "sign_in_count", default: 0, null: false
    t.datetime "updated_at", null: false
    t.index ["email"], name: "index_users_on_email", unique: true
    t.index ["organization_id", "role"], name: "index_users_on_organization_id_and_role"
    t.index ["organization_id"], name: "index_users_on_organization_id"
    t.index ["reset_password_token"], name: "index_users_on_reset_password_token", unique: true
  end

  create_table "webhook_events", id: :uuid, default: -> { "gen_random_uuid()" }, force: :cascade do |t|
    t.datetime "created_at", null: false
    t.text "error_message"
    t.string "external_event_id", null: false
    t.uuid "integration_id"
    t.uuid "organization_id"
    t.jsonb "payload", null: false
    t.datetime "processed_at"
    t.string "provider", null: false
    t.string "status", default: "pending", null: false
    t.index ["integration_id"], name: "index_webhook_events_on_integration_id"
    t.index ["organization_id"], name: "index_webhook_events_on_organization_id"
    t.index ["provider", "external_event_id"], name: "uq_webhook_provider_event", unique: true
    t.index ["status", "created_at"], name: "idx_webhook_pending", where: "((status)::text = 'pending'::text)"
  end

  add_foreign_key "clients", "integrations"
  add_foreign_key "clients", "organizations"
  add_foreign_key "conversations", "integrations"
  add_foreign_key "conversations", "organizations"
  add_foreign_key "integrations", "organizations"
  add_foreign_key "invoice_conversations", "conversations"
  add_foreign_key "invoice_conversations", "invoices"
  add_foreign_key "invoice_events", "invoices"
  add_foreign_key "invoice_events", "messages", on_delete: :nullify
  add_foreign_key "invoice_state_transitions", "invoices"
  add_foreign_key "invoice_state_transitions", "messages", column: "triggered_by_message_id", on_delete: :nullify
  add_foreign_key "invoices", "clients"
  add_foreign_key "invoices", "integrations"
  add_foreign_key "invoices", "organizations"
  add_foreign_key "messages", "conversations"
  add_foreign_key "outbox_messages", "conversations", on_delete: :nullify
  add_foreign_key "outbox_messages", "invoices"
  add_foreign_key "outbox_messages", "organizations"
  add_foreign_key "users", "organizations"
  add_foreign_key "webhook_events", "integrations"
  add_foreign_key "webhook_events", "organizations"
end
