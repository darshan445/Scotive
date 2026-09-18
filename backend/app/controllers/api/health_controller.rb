# frozen_string_literal: true

class Api::HealthController < ActionController::API
  def show
    render json: { ok: true, service: "scotive-api" }
  end
end
