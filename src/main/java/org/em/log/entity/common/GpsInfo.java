package org.em.log.entity.common;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class GpsInfo {

    @Column(nullable = false)
    private GpsStatus gpsStatus;

    private Double latitude;

    private Double longitude;
}
