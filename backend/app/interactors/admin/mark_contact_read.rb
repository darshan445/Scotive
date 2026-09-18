# frozen_string_literal: true

# Admin::MarkContactRead Interactor
# Purpose: mark a /contact submission as read.
# Methods:
# - execute

class Admin::MarkContactRead
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(id:)
    new(id: id).execute
  end

  def initialize(id:)
    @id = id
  end

  def execute
    execute_log_and_return_open_struct do
      row = ContactMessage.find_by(id: id)
      raise_string_error("Message not found") if row.blank?

      row.update!(status: "read")
      {
        id: row.id,
        status: row.status
      }
    end
  end

  private

  attr_reader :id
end
