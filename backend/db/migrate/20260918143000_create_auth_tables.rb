# frozen_string_literal: true

class CreateAuthTables < ActiveRecord::Migration[8.1]
  def change
    enable_extension "pgcrypto" unless extension_enabled?("pgcrypto")

    create_table :organizations, id: :uuid do |t|
      t.string :name, null: false
      t.timestamps
    end

    create_table :users, id: :uuid do |t|
      t.references :organization, type: :uuid, null: false, foreign_key: true
      t.string :email, null: false, default: ""
      t.string :encrypted_password, null: false, default: ""
      t.string :first_name
      t.string :last_name
      t.string :role, null: false, default: "member"
      t.string :reset_password_token
      t.datetime :reset_password_sent_at
      t.datetime :remember_created_at
      t.integer :sign_in_count, null: false, default: 0
      t.datetime :current_sign_in_at
      t.datetime :last_sign_in_at
      t.string :current_sign_in_ip
      t.string :last_sign_in_ip
      t.timestamps
    end

    add_index :users, :email, unique: true
    add_index :users, :reset_password_token, unique: true
    add_index :users, [ :organization_id, :role ]

    create_table :jwt_denylists, id: :uuid do |t|
      t.string :jti, null: false
      t.datetime :exp, null: false
      t.timestamps
    end

    add_index :jwt_denylists, :jti, unique: true
  end
end
