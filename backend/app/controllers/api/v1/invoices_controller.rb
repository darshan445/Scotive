# frozen_string_literal: true

module Api
  module V1
    class InvoicesController < Api::V1::BaseController
      def conversation
        result = ::Invoices::BuildConversation.execute(
          organization: current_organization,
          invoice_id: params[:id]
        )
        render_result(result, failure_status: :not_found)
      end

      def timeline
        result = ::Invoices::BuildTimeline.execute(
          organization: current_organization,
          invoice_id: params[:id]
        )
        render_result(result, failure_status: :not_found)
      end
    end
  end
end
