# frozen_string_literal: true

class ApplicationController < ActionController::API
  include Devise::Controllers::Helpers

  private

  def current_organization
    current_user&.organization
  end
end
