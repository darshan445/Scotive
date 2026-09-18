# frozen_string_literal: true

module LogHelper
  def log_error(error)
    call_stack = caller
    class_filename = self.class.to_s.underscore + ".rb"
    caller_info = call_stack.find { |line| line.include?(class_filename) }
    file_line_info = caller_info.match(/(.*):(\d+):in/)
    Rails.logger.error "███ ERROR! ███ file #{self.class} at [#{file_line_info[1]} line #{file_line_info[2]} ]: #{error} ███"
  end

  # Raises if the child interactor failed, so the parent execute block catches it.
  def validate_result(open_struct_result)
    return open_struct_result if open_struct_result.success?

    log_error(open_struct_result.errors.to_s)
    raise StandardError, open_struct_result.errors
  end

  # Like validate_result but does NOT raise — just logs and returns the struct.
  def validate_result_without_raising_error(open_struct_result)
    log_error(open_struct_result.errors.to_s) if open_struct_result.errors.present?

    open_struct_result
  end

  def raise_string_error(error_message_string)
    log_error(error_message_string)
    raise StandardError, error_message_string
  end

  # Convenience for controllers: returns .data on success, .errors on failure.
  def handle_open_struct_response(open_struct)
    open_struct.success? ? open_struct.data : open_struct.errors
  end
end
