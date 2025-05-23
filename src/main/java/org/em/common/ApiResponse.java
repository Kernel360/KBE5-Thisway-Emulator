package org.em.common;

import com.fasterxml.jackson.annotation.JsonInclude;
import org.springframework.http.HttpStatus;

public record ApiResponse<DATA>(int status, String message, @JsonInclude(JsonInclude.Include.NON_NULL) DATA data) {

    public static <DATA> ApiResponse<DATA> ok() {
        int status = HttpStatus.OK.value();

        return new ApiResponse<>(status, "", null);
    }

    public static <DATA> ApiResponse<DATA> ok(DATA data) {
        int status = HttpStatus.OK.value();

        return new ApiResponse<>(status, "", data);
    }

    public static <DATA> ApiResponse<DATA> created() {
        int status = HttpStatus.CREATED.value();

        return new ApiResponse<>(status, "", null);
    }

    public static <DATA> ApiResponse<DATA> noContent() {
        int status = HttpStatus.NO_CONTENT.value();

        return new ApiResponse<>(status, "", null);
    }

    public static <DATA> ApiResponse<DATA> error(ErrorCode errorCode) {
        int status = errorCode.getStatusValue();
        String message = errorCode.getMessage();

        return new ApiResponse<>(status, message, null);
    }
}
