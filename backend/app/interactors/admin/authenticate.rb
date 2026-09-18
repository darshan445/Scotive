# frozen_string_literal: true

# Admin::Authenticate Interactor
# Purpose: verify ops admin email/password from ENV.
# Methods:
# - execute

class Admin::Authenticate
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(email:, password:)
    new(email: email, password: password).execute
  end

  def initialize(email:, password:)
    @email = email.to_s.strip.downcase
    @password = password.to_s
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Invalid email or password") unless credentials_match?

      { email: expected_email }
    end
  end

  private

  attr_reader :email, :password

  def credentials_match?
    expected_email.present? &&
      expected_password.present? &&
      ActiveSupport::SecurityUtils.secure_compare(email, expected_email) &&
      ActiveSupport::SecurityUtils.secure_compare(password, expected_password)
  end

  def expected_email
    ENV["ADMIN_EMAIL"].to_s.strip.downcase
  end

  def expected_password
    ENV["ADMIN_PASSWORD"].to_s
  end
end
