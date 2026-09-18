# frozen_string_literal: true

# Admin::ListContactMessages Interactor
# Purpose: newest public /contact submissions for the ops inbox.
# Methods:
# - execute

class Admin::ListContactMessages
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(limit: 50)
    new(limit: limit).execute
  end

  def initialize(limit:)
    @limit = limit.to_i.clamp(1, 200)
  end

  def execute
    execute_log_and_return_open_struct do
      rows = ContactMessage.order(created_at: :desc).limit(limit)
      { messages: rows.map { |row| serialize(row) } }
    end
  end

  private

  attr_reader :limit

  def serialize(row)
    {
      id: row.id,
      name: row.name,
      email: row.email,
      company: row.company,
      message: row.message,
      status: row.status,
      created_at: row.created_at&.iso8601
    }
  end
end
