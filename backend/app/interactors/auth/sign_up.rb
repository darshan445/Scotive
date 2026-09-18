# frozen_string_literal: true

# Auth::SignUp Interactor
# Purpose: Create an organization + owner user and return a session payload.
# Methods:
# - execute

class Auth::SignUp
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(email:, password:, name: nil, timezone: nil)
    new(email: email, password: password, name: name, timezone: timezone).execute
  end

  def initialize(email:, password:, name:, timezone:)
    @email = email.to_s.strip.downcase
    @password = password.to_s
    @name = name.to_s.strip.presence
    @timezone = timezone
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Email is required") if email.blank?
      raise_string_error("Password is required") if password.blank?
      raise_string_error("Password must be at least 8 characters") if password.length < 8

      user = nil
      ActiveRecord::Base.transaction do
        organization = Organization.create!(name: derived_organization_name)
        user = User.new(
          organization: organization,
          email: email,
          password: password,
          password_confirmation: password,
          first_name: first_name,
          last_name: last_name,
          role: "owner"
        )
        raise_string_error(user.errors.full_messages.to_sentence) unless user.save
      end

      token = validate_result(Auth::EncodeJwt.execute(user: user)).data
      validate_result(Auth::SessionPayload.execute(user: user, token: token)).data
    end
  end

  private

  attr_reader :email, :password, :name, :timezone

  def derived_organization_name
    return "#{name}'s workspace" if name.present?

    local = email.split("@").first.presence
    local ? "#{local}'s workspace" : "My organization"
  end

  def first_name
    return if name.blank?

    name.split(/\s+/, 2).first
  end

  def last_name
    return if name.blank?

    name.split(/\s+/, 2)[1]
  end
end
