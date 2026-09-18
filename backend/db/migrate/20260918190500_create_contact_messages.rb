# frozen_string_literal: true

class CreateContactMessages < ActiveRecord::Migration[8.1]
  def change
    create_table :contact_messages, id: :uuid, default: -> { "gen_random_uuid()" } do |t|
      t.string :name
      t.string :email, null: false
      t.string :company
      t.text :message, null: false
      t.timestamps
    end
  end
end
