# frozen_string_literal: true

class Api::Auth::SessionsController < Devise::SessionsController
  respond_to :json
  skip_before_action :verify_authenticity_token, raise: false
  skip_before_action :authenticate_user!, only: :create, raise: false

  def create
    self.resource = warden.authenticate!(auth_options)
    sign_in(resource_name, resource)
    token = request.env["warden-jwt_auth.token"]
    render json: { user: user_payload(resource), token: token }, status: :ok
  end

  def destroy
    sign_out(resource_name)
    head :no_content
  end

  private

  def user_payload(user)
    {
      id: user.id,
      email: user.email,
      first_name: user.first_name,
      last_name: user.last_name,
      role: user.role,
      organization_id: user.organization_id
    }
  end
end
