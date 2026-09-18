# frozen_string_literal: true

# Auth::SessionPayload Interactor
# Purpose: Build the JSON session/user payload for auth responses.
# Methods:
# - execute

class Auth::SessionPayload
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(user:, token: nil)
    new(user: user, token: token).execute
  end

  def initialize(user:, token:)
    @user = user
    @token = token
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("User is required") if user.blank?

      payload = { user: user_hash }
      payload[:token] = token if token.present?
      payload
    end
  end

  private

  attr_reader :user, :token

  def user_hash
    {
      id: user.id,
      email: user.email,
      first_name: user.first_name,
      last_name: user.last_name,
      name: user.full_name,
      role: user.role,
      organization: {
        id: user.organization_id,
        name: user.organization.name
      }
    }
  end
end
