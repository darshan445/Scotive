# frozen_string_literal: true

module Api
  module V1
    module Qbo
      class PipelinesController < Api::V1::BaseController
        def show
          result = ::Quickbooks::PipelineStatus.execute(organization: current_organization)
          render_result(result)
        end

        def match
          result = ::Quickbooks::EnqueueConversationMatch.execute(organization: current_organization)
          render_result(result)
        end
      end
    end
  end
end
