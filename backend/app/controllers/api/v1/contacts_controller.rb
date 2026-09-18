# frozen_string_literal: true

module Api
  module V1
    class ContactsController < Api::V1::BaseController
      skip_before_action :authenticate_user!

      def create
        result = ::Contacts::Create.execute(
          name: params[:name],
          email: params[:email],
          company: params[:company],
          message: params[:message],
          website: params[:website]
        )
        render_result(result, status: :created)
      end
    end
  end
end
