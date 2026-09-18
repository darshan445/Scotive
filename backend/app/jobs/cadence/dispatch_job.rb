# frozen_string_literal: true

class Cadence::DispatchJob < ApplicationJob
  queue_as :default

  def perform
    OutboxMessage.due_to_send.find_each do |row|
      Cadence::Dispatch.execute(outbox_message: row)
    end
  end
end
