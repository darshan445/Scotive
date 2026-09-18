# frozen_string_literal: true

class AddCadenceStepToOutboxMessages < ActiveRecord::Migration[8.1]
  def change
    add_column :outbox_messages, :cadence_step, :string
    add_index :outbox_messages, [ :invoice_id, :cadence_step ],
              unique: true,
              where: "status IN ('scheduled', 'draft') AND cadence_step IS NOT NULL",
              name: "uq_outbox_pending_step"
  end
end
