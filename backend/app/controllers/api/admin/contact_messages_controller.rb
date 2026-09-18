# frozen_string_literal: true

module Api
  module Admin
    class ContactMessagesController < Api::Admin::BaseController
      def index
        result = ::Admin::ListContactMessages.execute(limit: params[:limit])
        render_result(result)
      end

      def read
        result = ::Admin::MarkContactRead.execute(id: params[:id])
        render_result(result, failure_status: :not_found)
      end
    end
  end
end
