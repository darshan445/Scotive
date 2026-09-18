# frozen_string_literal: true

class Api::Auth::RegistrationsController < Devise::RegistrationsController
  respond_to :json
  skip_before_action :verify_authenticity_token, raise: false
  skip_before_action :authenticate_user!, only: :create, raise: false

  def create
    org = Organization.create!(name: org_name)
    build_resource(sign_up_params.merge(organization: org, role: "owner"))
    resource.save
    if resource.persisted?
      sign_in(resource_name, resource)
      token = request.env["warden-jwt_auth.token"]
      render json: {
        user: {
          id: resource.id,
          email: resource.email,
          first_name: resource.first_name,
          last_name: resource.last_name,
          role: resource.role,
          organization_id: resource.organization_id
        },
        token: token
      }, status: :created
    else
      org.destroy
      render json: { errors: resource.errors.full_messages }, status: :unprocessable_entity
    end
  rescue ActiveRecord::RecordInvalid => e
    render json: { errors: [e.message] }, status: :unprocessable_entity
  end

  private

  def org_name
    params.dig(:organization_name).presence ||
      params.dig(:user, :organization_name).presence ||
      "My organization"
  end

  def sign_up_params
    params.require(:user).permit(:email, :password, :password_confirmation, :first_name, :last_name)
  rescue ActionController::ParameterMissing
    params.permit(:email, :password, :password_confirmation, :first_name, :last_name)
  end
end
