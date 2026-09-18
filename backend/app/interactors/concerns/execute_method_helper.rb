# frozen_string_literal: true

require "ostruct"
require_relative "log_helper"

module ExecuteMethodHelper
  include LogHelper

  # Wraps the execute block: success returns OpenStruct(success?: true, data: <last value>).
  # Any StandardError is caught and returns OpenStruct(success?: false, errors: <message>).
  def execute_log_and_return_open_struct(&block)
    data = block.call
    OpenStruct.new(success?: true, data: data)
  rescue StandardError => e
    log_error(e)
    OpenStruct.new(success?: false, errors: e.message)
  end
end
