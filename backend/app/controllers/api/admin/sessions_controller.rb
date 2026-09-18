# frozen_string_literal: true

module Api
  module Admin
    class SessionsController < Api::Admin::BaseController
      skip_before_action :require_admin!, only: :create

      def create
        result = ::Admin::Authenticate.execute(email: params[:email], password: params[:password])
        session[:admin_email] = result.data[:email] if result.success?
        render_result(result, failure_status: :unauthorized)
      end

      def show
        render json: { data: { email: session[:admin_email] } }
      end

      def destroy
        session.delete(:admin_email)
        head :no_content
      end
    end
  end
end
