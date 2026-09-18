# frozen_string_literal: true

class ApplicationController < ActionController::API
  include Devise::Controllers::Helpers

  before_action :authenticate_user!, unless: :devise_controller?

  private

  def current_organization
    current_user&.organization
  end
end
