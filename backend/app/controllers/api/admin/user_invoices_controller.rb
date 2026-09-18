# frozen_string_literal: true

module Api
  module Admin
    class UserInvoicesController < Api::Admin::BaseController
      def index
        result = ::Admin::UserInvoices.execute(user_id: params[:user_id], limit: params[:limit])
        render_result(result, failure_status: :not_found)
      end
    end
  end
end
